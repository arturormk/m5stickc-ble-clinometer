# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **tests** — `test_stop_stream` and `test_stream_packets` had a race condition
  where `send("START_STREAM …")` could return an in-flight `TILT` packet
  (instead of `OK STREAM …`) and leave the start-ack unread in the notification
  queue. In `test_stop_stream` the stale `OK STREAM 200` was then silently
  skipped by `recv_matching("OK STREAM")` — correct by accident because
  `"OK STREAM 200".startswith("OK STREAM")` is true and could match before
  `"OK STREAM 0"`. Both tests are rewritten to use `send_no_wait` +
  `recv_matching("OK STREAM 200")` for the start round-trip so every command
  ack is explicitly consumed by the call that requested it, and no legitimate
  response can become accidental noise. The stop round-trip uses the precise
  prefix `"OK STREAM 0"` in both tests.

- **Firmware** — BLE command processing no longer runs inside the Bluedroid
  `onWrite()` callback. Previously, all command dispatch — float formatting,
  `snprintf`, sidereal arithmetic, NVS calls — executed synchronously on the
  BLE FreeRTOS task. On the M5StickS3 this triggers the Bluedroid task
  watchdog and resets the device, making every non-trivial command
  (`GET_TILT`, `GET_STATUS`, `SET_TIME`, `CALIBRATE`, …) fail with a
  timeout. The fix moves processing to the main Arduino task: `onWrite()` now
  only copies the raw command bytes to a `volatile pendingBleCommand[256]`
  buffer and sets a flag; `BleManager::update()` (called from `loop()`)
  drains the flag, runs `processCommand()`, and then sends the response as
  before. This is consistent with the existing deferred-send pattern for
  `pendingBleResponse`. The Plus2 is unaffected by the watchdog but benefits
  from the same robustness margin if command complexity grows.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **Firmware / tests** — `GET_BOARD` now recognises the M5StickS3.
  `boardTypeName()` in `BleManager.cpp` gains a `board_M5StickS3` case
  returning `"M5StickS3"`, and `_KNOWN_BOARDS` in `test_commands.py` is
  extended to match.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).

- **m5ctl** — `set-time-now --timezone TZ` now uses the timezone string (`TZ`)
  as the device display label when `--label` is not given, instead of sending no
  label and letting the device fall back to the UTC offset from the ISO8601
  timestamp (e.g. `+02:00`). Explicit `--label` still takes priority.

### Added
- **m5ctl** — `script FILE` subcommand: reads m5ctl command invocations from a
  file (or stdin when `FILE` is `-`), one per line, and runs them all over a
  single BLE connection. Each line is parsed as m5ctl arguments
  (`set-time-now --timezone CEST`, `beep C4`, …) rather than raw BLE strings,
  so high-level commands such as `set-time-now` work directly in script files
  without shell date formatting. Blank lines and `#` comments are ignored.
  Non-batchable commands (`listen`, `exec`, `scan`, `list`, …) produce a
  warning and are skipped rather than aborting the run.
- **m5ctl 1.1** — `exec FILE` subcommand: reads raw BLE commands from a file
  (or stdin when `FILE` is `-`), sends them one at a time over a single BLE
  connection, and prints each response. Blank lines and lines starting with `#`
  are silently skipped, allowing comments in script files.
- **m5ctl 1.1** — `-p` / `--print-cmd` global flag: prints the raw BLE command
  string to stderr (prefixed with `>>>`) before each write. Works for all
  subcommands including `exec`.
- Clinometer dirty-check: `Display::update()` now skips the SPI DMA flush on
  `SCREEN_CLINOMETER` when no display-relevant state has changed since the last
  render — angles within 0.1°, and identical values for `batteryLevel`,
  `bleConnected`, `nightMode`, `imuAvailable`, `upsideDown`, `pitchAxis`, and
  `rollAxis`. On a stationary device this eliminates continuous SPI bus traffic,
  freeing CPU bandwidth for BLE heartbeats (relevant on large-screen devices such
  as Core2 and Grey) and reducing average current draw on all devices.
  Proposed by [@senshu-hiro2](https://github.com/hiroyukisenshu-commits).
- Auto-dim: the backlight drops to a low level (`BRIGHTNESS_DIM = 30`) after
  60 seconds with no BLE command received **and** no tilt change exceeding 5° on
  either axis. Full brightness (`BRIGHTNESS_FULL = 128`) resumes immediately on
  the next BLE command or when the device is moved past the threshold. While tilt
  streaming is active the display is kept at full brightness regardless of elapsed
  time. Night mode sets its own fixed dim level (`BRIGHTNESS_NIGHT = 40`) and
  bypasses the inactivity logic entirely.
- Firmware version string (`FW_VERSION`) defined in `src/version.h`. The version
  is now surfaced in two places: the `GET_STATUS` BLE response gains a `FW=`
  field (e.g. `… NIGHT=0 FW=1.1`), and the BATTERY screen shows
  "Firmware ver 1.1" in cyan near the bottom of the display.

### Fixed
- **m5ctl / tests** — on Windows, `BleakDeviceNotFoundError` during a connection
  attempt is no longer a near-instant failure. WinRT's
  `FromBluetoothAddressAsync` returns "not found" immediately when the target
  device is absent from the OS Bluetooth advertisement cache (e.g. it has not
  yet restarted advertising after a previous disconnect). This caused the retry
  loop's backoff sleeps to be the only waiting mechanism, and with fast-failing
  retries the three attempts could be exhausted in under a second — before the
  device had finished re-advertising. The fix adds an explicit
  `BleakScanner.find_device_by_address()` pre-scan on Windows before each
  `connect()` call (in both `_connect()` in `m5ctl` and `BleSession._do_connect()`
  in the test fixtures). The scanner waits up to `CONNECT_TIMEOUT` seconds for
  the device to appear in advertisements, converting an instant cache-miss into a
  patient scan. This mirrors the `dangerous_use_bleak_cache` workaround already
  in place for the analogous Linux/BlueZ re-advertising problem.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl** — BLE connection retries now correctly handle `TimeoutError` and
  `asyncio.CancelledError`, both of which Bleak's WinRT backend raises on
  Windows when the connection handshake times out (`asyncio.timeout()` cancels
  the internal session-status wait and the resulting `CancelledError` is
  re-raised as `TimeoutError`). Neither is a `BleakError` subclass, so
  previously they escaped the retry loop and crashed the program with an
  unhandled traceback. The `run()` top-level handler is widened to match so
  exhausted retries still print a clean `BLE error: …` message.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl** — after a failed `connect()` attempt, `client.disconnect()` is
  now called before the next retry. A connection failure leaves the underlying
  BLE adapter (particularly the WinRT stack on Windows) in a partially-active
  state; without an explicit release, each retry creates a new `BleakClient`
  on top of unreclaimed resources, which can cause the next attempt to time out
  for the same reason as the first. Calling `disconnect()` lets the adapter
  fully reset between attempts, giving each retry a clean slate.
  Unit tests for `_connect()` are updated to match the new `disconnect()`
  call counts: one cleanup call per failed attempt, plus the normal teardown
  call when a connection eventually succeeds.
- **m5ctl `exec` / `script`** — passing a non-existent file path no longer
  produces a Python traceback. The tool now checks for file existence before
  attempting to read and exits with `error: file not found: '<path>'` on stderr.
  (`-` for stdin is unaffected.) Reported by
  [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl `script`** — error messages now include the original file line number
  (`error: script line 7: bad command: '...'`), making it easier to locate the
  offending line in the script file. Blank lines and comments are counted when
  computing the line number so it always matches the editor's line count.
- **tests** — the three `_connect` retry unit tests (`test_connect_first_attempt_succeeds`,
  `test_connect_retries_on_transient_failure`, `test_connect_raises_after_all_retries_exhausted`)
  now fail on Windows with `BleakDeviceNotFoundError` or a wrong `connect()` call count.
  The `_mock_ble` helper patched `BleakClient` and `asyncio.sleep` but left `BleakScanner`
  unpatched. On Windows `_connect()` calls `BleakScanner.find_device_by_address()` before
  `client.connect()`, so the real BLE stack was hit, found no device, and the synthesised
  `BleakDeviceNotFoundError` either escaped (tests 1 & 2) or was caught but with
  `connect()` never called (test 3's call-count assertion). Fixed by also patching
  `BleakScanner` in `_mock_ble` with `find_device_by_address` returning a fake device,
  so every retry test reaches `client.connect()` as intended.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).

### Changed
- CI: add `workflow_dispatch` trigger so releases can be created manually from
  the GitHub Actions UI without pushing a tag.

### Fixed
- README: removed a stale paragraph describing auto-rotation behaviour that was
  no longer accurate.

### Removed
- Shutdown melody in `PowerManager::deepSleep()`: the blocking `tone()`+`delay()`
  sequence that played four descending notes before powering off stopped working
  after the migration to M5Unified. The device now powers off silently.

## [1.0.0] — 2026-05-31

First public release. Pre-built firmware for the M5StickC Plus 2 is attached
to the [GitHub Release](../../releases/tag/v1.0.0); other boards must be built
from source with PlatformIO.

### Features at release
- Bubble-level clinometer with 1°/2°/3° concentric rings and numeric Pitch/Roll
  readout; display-smoothed angles via exponential filter.
- BLE GATT service (`M5-NexStar-Level`) with a full command set: `GET_TILT`,
  `CALIBRATE`, `SET_TIME`, `SET_TIME_ZONE`, `SET_LONGITUDE`, `SET_RADEC`,
  `SET_ALTAZ`, `SHOW_MSG`, `SHOW_MSG_WAIT`, `START_STREAM`, `SET_NIGHT_MODE`,
  `GET_PITCHROLL` / `SET_PITCHROLL`, `BEEP`, `PERSIST`, `REBOOT`, and more.
- Six display screens: Clinometer, Time (solar/sidereal), RA/Dec, Alt/Az,
  Battery, Message overlay.
- Night mode — all display colours shifted to red/orange-red.
- Configurable pitch/roll axis assignment (`SET_PITCHROLL`), persisted to NVM.
- NVM persistence for timezone, UTC offset, observer longitude, calibration
  vector, and pitch/roll axes; single-write validity flag for safe power-loss
  handling.
- Hardware RTC sync (`SET_TIME` writes PCF8563; restored on boot). RTC-less
  devices (M5Stack Grey) tick correctly per session without flash persistence.
- Multi-board support via M5Unified: M5StickC Plus 2, Core2, CoreS3, Grey;
  display layout and IMU axis mapping adapt at runtime.
- `m5ctl` Python CLI for the full BLE command interface, including multi-device
  config, `set-time-now`, `set-timezone` with IANA/abbreviation resolution,
  `listen --stream`, and `m5ctl list` / `scan`.
- Real-time 3D orientation viewer (`tests/3d_model.py`, pygame + PyOpenGL).
- Pytest suite exercising the full BLE command interface against a real device.

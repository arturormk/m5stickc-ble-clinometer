# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Firmware / Display** — `SET_BRIGHT <0-255>|AUTO` BLE command: sets a fixed backlight level (0–255) and suspends the autodim system, or restores autodim (`AUTO`). The autodim ceiling when active remains 128; `SET_BRIGHT` allows the full 0–255 hardware range. Night mode is overridden by a subsequent `SET_BRIGHT`. The command is proposed by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **Firmware / Display** — front button (BtnA) long-press (≥ 1 s) cycles through five brightness presets — `255 → 128 → 32 → 1 → auto → 255 → …` — and plays a distinct tone at each step: higher pitch for higher brightness, stepping through the notes of an A minor chord (A6/1760 Hz → E6/1319 Hz → C6/1047 Hz → A5/880 Hz), with a double-beep at the A6/1760 Hz pitch (60 ms gap) when the cycle wraps to auto. Reaching the `auto` step re-enables autodim, making BLE unnecessary to return to automatic brightness control. Short-press continues to cycle screens as before. Tone idea proposed by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **Firmware / BLE** — `GET_STATUS` response gains a `BRIGHT=` field: `BRIGHT=AUTO` when autodim is active, `BRIGHT=<n>` when a manual level is set.
- **m5ctl** — `set-bright <0-255|auto>` subcommand: sets backlight level or restores autodim; validates range 0–255 client-side and exits with an error message for out-of-range or non-numeric, non-`auto` input.
- **m5ctl** — `run FILE` subcommand: executes m5ctl commands from a file (or stdin when `FILE` is `-`) sequentially over a single BLE connection, with support for `! directive` lines that control timing, looping, interaction, and output validation. Available directives: `! wait <seconds>`, `! at HH:MM:SS`, `! for N` / `! endfor`, `! echo <text>`, `! expect <prefix>`, `! wait_tilt [<degrees>]`, `! exit`, `! timeout <secs> <directive>`, `! if <name>` / `! if_not <name>` / `! else` / `! endif`, `! set <name>`, `! unset <name>`. Unlike `script`, which batches all commands and sends them at once, `run` executes each item in order, inserting sleeps, loops, and event waits as it goes — making it suitable for demos, video narration, and timed automation. Proposed by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl `run`** — `! timeout <secs> <directive>` modifier: wraps a `! expect` or `! wait_tilt` directive with a wall-clock deadline. If the inner directive completes before the deadline, execution continues normally; if the deadline expires, execution continues silently. `! timeout` writes to the reserved flag `timedout`, readable via `! if timedout` / `! if_not timedout`.
- **m5ctl `run`** — `! if <name>` / `! if_not <name>` / `! else` / `! endif`: conditional blocks gated on named boolean flags. Flags are script-global, set by `! set <name>` at runtime or pre-injected via `--set NAME` on the command line (repeatable). The reserved flag `timedout` is set/cleared automatically by `! timeout`. Parse-time validation catches orphan `! else` / `! endif`, unclosed blocks, duplicate `! else`, and invalid identifiers.
- **m5ctl `run`** — `! unset <name>`: clears a named flag at runtime. Silent no-op if the flag is not currently set; has no effect inside a skipped block. Complements `! set` and makes it possible to clear a CLI-supplied `--set` flag for a specific script section (e.g. temporarily re-enable an interactive section inside an otherwise non-interactive run).
- **m5ctl `run --set NAME`** — pre-sets a named flag before the script starts. Repeatable. Example: `m5ctl run --set noninteractive demo.m5s` to skip interaction-dependent sections without modifying the script.
- **`tools/demo.m5s`** — button and tilt interaction sections now use `! timeout 10 expect` / `! timeout 10 wait_tilt` with `! if timedout` / `! else` / `! endif` blocks, so an unattended run completes automatically after 10 seconds per section while a user who interacts within 10 seconds still sees the interactive response.
- **m5ctl** — `terminal` subcommand (alias `term`): opens an interactive BLE terminal over a persistent connection. Type m5ctl sub-commands (`tilt`, `set-screen CLINOMETER`, …) or raw BLE strings (`GET_TILT`, …); all BLE notifications print to stdout as they arrive, interleaved with the `m5>` prompt. Input history is persisted to `~/.m5ctl_history` on platforms where the `readline` module is available. Type `exit` or press Ctrl+D to close the connection.
- **`tools/demo.m5s`** — full-device demo script showcasing all `run` directives and major firmware features: connectivity check, screen navigation, live tilt readings, night mode, melody playback, button interaction, and tilt detection. Run with `uv run tools/m5ctl -p run tools/demo.m5s`.
- **Firmware / Power** — Holding the physical **Power switch** (BtnPWR, GPIO 35 on M5StickC Plus2) now plays a descending tone (A6→E6→A5, 1760→1319→880 Hz) starting ~1.7 s into the hold, as a power-down cue. The board's own hardware power circuit cuts power autonomously around the 2 s mark — firmware cannot control, delay, or even observe that cutoff — so the cue is timed to finish (or be audibly cut short) right as the device powers down.
- **`monitor`** — convenience script wrapping `pio device monitor`; reads `PIO`/`PORT` env vars with sensible defaults (`~/.platformio/penv/bin/pio`, `/dev/ttyACM0`).
- **m5ctl** — `m5ctl version` now tracks the firmware's `FW_VERSION`. The pre-commit hook keeps `tools/m5ctl`'s `_VERSION` constant in sync, stamping it only in commits that already touch `m5ctl` or when the MAJOR.MINOR version changes, so it stays a standalone file with no added no-op commits.

### Fixed
- **Firmware / Buttons** — BtnB's long-press (≥2 s) was previously wired to call `M5.Power.powerOff()`, documented as "power off". On M5StickC Plus2 (which has no AXP-style PMIC) that call doesn't perform a real hardware power-off — it silently resets the device instead, with no audible feedback, and was never actually shutting the device down. BtnB's long-press handling (and the now-unreachable `PowerManager::deepSleep()`) has been removed entirely; BtnB is a pure short-press control (reboot / System Info navigation). The physical Power switch is the only control that actually powers the device off, and it always worked correctly via the board's own hardware — see Added, above, for the new tone cue on that path.
- **Firmware / Brightness** — BtnA long-press from autodim mode now always jumps to the highest preset (255/A6) on the first press, giving an immediate visible change. The previous dynamic-anchoring heuristic (which tried to land on the nearest preset below the current physical brightness) has been superseded by the new five-step cycle that includes auto as an explicit stop.
- **Firmware / Battery** — Battery voltage display now shows `-- V` instead of an
  implausible fixed value (~6.30 V) when an ENV III Unit is connected via the Grove
  port on the M5StickC Plus 2. The anomalous reading is caused by an M5Unified library
  bug (reported upstream by the same contributor); readings above 5.0 V (impossible for
  any supported LiPo cell) are now discarded and displayed as unavailable (`-- V`).
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl `set-radec`** — negative declinations (e.g. `set-radec 06:45:09 -16:42:58`) were
  rejected by argparse with `error: the following arguments are required: dec` because
  argparse interprets any token starting with `-` that does not look like a bare number as
  a flag. Fixed by adding a `~`-sentinel preprocessing step in `_preprocess_argv()` — the
  same mechanism already used for `set-timezone` (negative UTC offsets) and `set-pitchroll`
  (negative axis codes) — that rewrites a leading `-` in the DEC argument to `~` before
  parsing and restores it in the dispatch handler before sending the BLE command.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl** — on Windows, `_connect()` could hang indefinitely if the target device
  went away (e.g. powered off) between the Windows pre-scan and the actual GATT
  handshake. `BleakClient`'s own `timeout` constructor argument only bounds Bleak's
  internal address-resolution scan, not `connect()` itself, so a vanished device left
  the handshake with no enforced ceiling. `connect()` is now wrapped in
  `asyncio.wait_for(..., timeout=timeout)` on every platform, so a stuck handshake
  always fails after `timeout` seconds instead of hanging forever.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **m5ctl** — pressing Ctrl+C during a connection attempt produced a crash
  (`Task was destroyed but it is pending!` / a `ProactorEventLoop.__del__`
  traceback on Windows) instead of a clean exit. `_connect()`'s retry loop caught
  `asyncio.CancelledError` together with ordinary BLE errors and looped back into
  another sleep-and-retry cycle, which kept the task running after `asyncio.run()`
  had already begun cancelling it during shutdown. `CancelledError` now gets its
  own handler that disconnects and re-raises immediately, with no retry.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).
- **3D viewer (`tests/3d_model.py`)** — brought the BLE worker's connection handling up
  to par with the `m5ctl` fixes above. `client.connect()` is now wrapped in
  `asyncio.wait_for(..., timeout=10.0)`, so a device that disappears mid-handshake can no
  longer hang the worker thread forever (same root cause as the `m5ctl` Windows hang,
  above). The worker's bare `except Exception` clauses are narrowed to
  `(BleakError, asyncio.TimeoutError, OSError)`, so a genuine programming bug surfaces
  instead of being silently retried forever behind the on-screen "error" text; the
  `finally` block still unconditionally disconnects the BLE client regardless of which
  exception type propagates. Separately, pressing Ctrl+C during the main render loop
  previously skipped the existing graceful-shutdown block entirely (no `STOP_STREAM`,
  no clean `disconnect()`, no `renderer.quit()`) because `KeyboardInterrupt` was never
  caught; the render loop is now wrapped in `try/except KeyboardInterrupt` so Ctrl+C
  falls through to that shutdown path instead of crashing past it.

- **m5ctl** — script files read by `exec`, `script`, and `run`, as well as the device
  config file, were opened with `pathlib.Path.read_text()` without an explicit `encoding=`
  argument. On Windows, Python falls back to the system ANSI code page (CP932 on Japanese
  systems, CP1252 on Western systems), causing `UnicodeDecodeError` on any UTF-8 script
  file. Fixed by passing `encoding="utf-8"` to all four `read_text()` call sites in the
  tool.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).

- **m5ctl `run`** — `! expect <prefix>` no longer times out when placed immediately after a plain BLE command. Previously the command handler always consumed the first device reply with `queue.get()`, leaving nothing for `! expect` to match — so `ping` / `! expect OK PONG` always timed out. The fix adds a look-ahead in `cmd_run`: when the next item in the expanded items list is an `_Expect`, the command handler skips its auto-consume and lets `! expect` drain the queue instead. The `! expect` loop already prints every notification it reads until the prefix matches, so multi-event flows (e.g. `show-msg … / ! expect EVENT SCREEN MESSAGE`) continue to work correctly.
- **Build / M5StickC Plus 2** — `[env:m5stickc-plus2]` was missing
  `BOARD_HAS_PSRAM` and `-mfix-esp32-psram-cache-issue`. The Plus 2 ships
  with 2 MB PSRAM; without `BOARD_HAS_PSRAM` the Arduino/ESP-IDF layer does
  not initialise the PSRAM heap, and without the cache-fix flag the compiler
  can generate incorrect code for the ESP32 PSRAM cache errata.
  `CORE_DEBUG_LEVEL=0` is added explicitly so the environment is
  self-contained when overriding the base `build_flags`.
- **Build / M5Stack Core2** — `[env:m5stack-core2]` was missing the same two
  flags for the same reasons (Core2 also carries PSRAM on an ESP32).
  `CORE_DEBUG_LEVEL=0` added for the same self-containment reason.
- **Build / M5Stack CoreS3** — `[env:m5stack-cores3]` was missing
  `CORE_DEBUG_LEVEL=0` and `BOARD_HAS_PSRAM`. (`-mfix-esp32-psram-cache-issue`
  is not applicable to the ESP32-S3 and is intentionally absent.)
- **Docs / 3D viewer** — the keyboard shortcut table in the README was missing
  the `4` → M5StickS3 entry. Key `4` has been functional since v1.2.0 but was
  not documented.
- **Firmware / Display** — the clinometer screen now keeps updating for 30 seconds after
  a `CALIBRATE` or `CALIBRATE_RESET` command (and after any tilt change exceeding 0.1°)
  before the power-saving "skip unchanged frame" guard activates. Previously the guard
  fired immediately on the first stable frame, so the bubble appeared frozen right
  after calibration even though the reference angle had shifted.

## [1.2.0] — 2026-06-10

### Fixed
- **Firmware / BLE** — `GET_STATUS` no longer returns `SCREEN=UNKNOWN` when the
  device is on a System Info page (1/4–4/4). `screenName()` now maps
  `SCREEN_SYSINFO_1`–`SCREEN_SYSINFO_4` to `SYSINFO-1`–`SYSINFO-4`.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).

- **3D viewer** — IMU axis arrows (toggled with `C`) are now drawn in the
  physically correct model-space directions for each device. Previously
  `draw_axes()` always used the fixed GL frame `(1,0,0)`, `(0,1,0)`,
  `(0,0,1)`, which happened to coincide with the IMU axes for the Plus 2 and
  Core2/CoreS3 but are wrong for the M5StickS3. Directions are now derived
  from each model's `pitch_axis` field:
  - `'X'` (Plus 2): IMU +X = GL +X (= UX −Y), IMU +Y = GL +Y (= UX +X) — unchanged
  - `'NXY'` (S3): IMU +X = GL −Y (= UX −X), IMU +Y = GL +X (= UX −Y) — fixed
  - `'Y'` (Core2/CoreS3): UX = IMU frame — unchanged

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

- **Firmware / M5StickS3** — corrected screen orientation and IMU-to-UX axis
  mapping. The display now uses `setRotation(3)` (same as the StickC Plus
  family), placing the blue button on the right — consistent with the
  M5StickC Plus 2 and keeping the USB-port recess on the same edge for
  telescope-ring mounting. The IMU axis mapping is updated to match:
  UX +X = IMU −X, UX +Y = IMU −Y, UX +Z = IMU +Z (hardware-verified).
  Previously the device used `setRotation(1)` (button on left) with an
  identity UX ↔ IMU mapping. `docs/adr/m5_imu_axes.jpg` is updated to
  include the StickS3 axis diagram.
  Contributed by [@senshu-hiro2](https://github.com/senshu-hiro2).

- **Firmware / M5StackCoreS3** — speaker volume now initialised to 40 for
  `board_M5StackCoreS3`, consistent with Core2 and Grey. Previously this
  board fell through to the 50-volume default.
  Contributed by [@senshu-hiro2](https://github.com/senshu-hiro2).

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

- **Firmware / M5StickS3** — BLE commands intermittently hung on the
  M5StickS3. The fix makes the two local buffers inside `processCommand()`
  (`cmd[256]` and `resp[160]`) `static`, removing 416 bytes of stack pressure
  from the Arduino loop task on every command dispatch. Both buffers are fully
  overwritten at the start of each call so the change is semantically neutral.
  Reported by [@senshu-hiro2](https://github.com/senshu-hiro2).

- **m5ctl** — `set-time-now --timezone TZ` now uses the timezone string (`TZ`)
  as the device display label when `--label` is not given, instead of sending no
  label and letting the device fall back to the UTC offset from the ISO8601
  timestamp (e.g. `+02:00`). Explicit `--label` still takes priority.

### Added
- **`SET_SCREEN` BLE command** — navigates to any named screen directly over BLE:
  `CLINOMETER`, `TIME`, `RADEC`, `ALTAZ`, `BATTERY`, `SYSINFO-1` through
  `SYSINFO-4`. Returns `OK SCREEN <name>`. `MESSAGE` is excluded (use `SHOW_MSG`
  instead). Primarily useful for test automation and integration scripts.
- **m5ctl** — `set-screen NAME` subcommand wraps `SET_SCREEN`; the valid name list
  is enforced by argparse before any BLE connection is made.
- **tests** — `test_set_screen_reports_correct_name` (parametrized over all nine
  navigable screens including every SYSINFO page) and
  `test_get_status_screen_field_is_known` guard against future regressions.

- **3D viewer** — M5StickS3 model added to `tests/3d_model.py`. Body
  dimensions and UX/GL axis layout are identical to the M5StickC Plus 2 (same
  landscape camera eye, same screen inset, same `ux_x_gl` / `ux_neg_y_gl`);
  only the IMU ↔ UX mapping differs (`pitch_axis='NXY'`: UX +X = IMU −X,
  UX +Y = IMU −Y). `BOARD_TO_MODEL` maps the `"M5StickS3"` `GET_BOARD`
  response to the new entry so the viewer auto-selects the correct model on a
  live connection. Key `4` selects it manually; `--model 4` is the new CLI
  option.

- **System Info screens** — four read-only diagnostic pages accessible from the
  Battery screen via a short side-button (BtnB) press. The pages are not part of
  the main front-button cycle; repeated short presses step through them and wrap
  back to Battery.
  - **Page 1/4 — STATUS:** firmware version, uptime, IMU die temperature (°C,
    from the MPU6886/BMI270 on-die sensor), and battery charging state (CHG/DSG
    from the PMIC; `--` on boards that use a plain ADC for battery measurement,
    such as the M5StickC Plus 2, where no charging status is available through
    the SDK).
  - **Page 2/4 — STACK:** loop-task and BTC-task stack high-water marks shown as
    peak-used / total bytes (`uxTaskGetStackHighWaterMark × sizeof(StackType_t)`)
    with a colour-coded 10-segment bar each (dark green ≤ 60%, amber ≤ 80%, red
    above 80%). The BTC-task row is only shown on builds where
    `CONFIG_BT_BTC_TASK_STACK_SIZE` is defined (M5StickS3).
  - **Page 3/4 — HEAP:** heap total, free, min-free watermark, max-alloc block,
    and PSRAM free (shown as `none` on boards without PSRAM).
  - **Page 4/4 — SYSTEM INFO:** chip model and revision, core count and CPU
    frequency, flash chip size, sketch used/free, IDF SDK version.
  - Pressing the front button from any System Info page advances to the
    Clinometer screen (same as pressing it from Battery).
  - Firmware version display moved from the Battery screen to System Info page 1.

- **M5StickS3 support** — new `[env:mstickS3]` PlatformIO environment for the
  M5StickS3 (ESP32-S3, 8 MB flash, PSRAM). Includes the flags required for
  correct operation: `BOARD_HAS_PSRAM`, `-mfix-esp32-psram-cache-issue`,
  `ARDUINO_USB_CDC_ON_BOOT=1`, `ARDUINO_USB_MODE=1`. Speaker volume is
  initialised to 128 for this board. The base platform is upgraded from
  `espressif32@6.1.0` to `espressif32@^7.0.1`, aligning all environments on
  the same major version (CoreS3 already required 7.x).
  Machine-specific upload/monitor port settings belong in a `platformio.ini.local`
  file (now `.gitignore`d) rather than in the shared `platformio.ini`.
  Contributed by [@senshu-hiro2](https://github.com/senshu-hiro2).
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
- **STACK page** — each task block now shows a small `heap: N B` annotation
  (Font0, dark grey) between the peak-used/total text line and the bar. The
  value comes from `heap_caps_get_allocated_size(pxTaskGetStackStart(handle))`
  and reflects the actual heap block committed to the task stack by the ESP32
  TLSF allocator — always slightly larger than the configured size due to
  free-list block rounding (~512 B on typical builds). For the BTC task this
  serves as a runtime sanity check: the bar's denominator is
  `CONFIG_BT_BTC_TASK_STACK_SIZE`, but that task's stack is precompiled into
  `libbt.a` and cannot actually be changed by redefining the macro. If the
  macro value and the `heap:` annotation diverge significantly, the config is
  misleading and the bar scale is wrong. Bar colours brightened from
  `TFT_DARKGREEN` (~40% RGB565 saturation) to 75% for all three threshold
  levels; thresholds unchanged (green ≤ 60%, amber ≤ 80%, red > 80%).
- **Battery screen** — navigation hint replaced: the centred `"B: system info"` text at the
  bottom is now a compact `[B]` icon at the bottom-right corner.
- **System Info screens** — expanded from three pages to four. A dedicated
  **STACK page (2/4)** was inserted between STATUS (1/4) and HEAP (3/4); the old
  Chip page shifts to 4/4 and retains the title `SYSTEM INFO`. Each page title is
  now displayed in the header so the subject is immediately clear on entry.
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

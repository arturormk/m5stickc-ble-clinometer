# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

# M5StickC Plus 2 Bluetooth Clinometer

A BLE-enabled clinometer and telescope status display for the M5StickC Plus 2 (ESP32). Used to align a NexStar Alt/Az GoTo telescope mount and display live coordinates sent from a Raspberry Pi.

![Bubble Level](docs/images/clinometer_bubble.jpg)

![UTC](docs/images/clinometer_utc.jpg)

![RA Dec](docs/images/clinometer_radec.jpg)

![Alt Az](docs/images/clinometer_altaz.jpg)

## What it does

- Shows a live **bubble level** (clinometer) based on the built-in IMU — used to level the telescope mount
- Displays **time**, **RA/Dec**, and **Alt/Az** coordinates pushed from the Raspberry Pi over BLE
- Exposes a **BLE GATT service** so a Raspberry Pi can query tilt angles and update the displayed data at any time, regardless of which screen is active
- Supports **operator messages** — the Pi can push short text to the display, optionally waiting for a button acknowledgement
- Supports **night mode** — switches all display colours to red/orange-red to preserve dark-adapted vision at the eyepiece

## Hardware

| Item | Detail |
|---|---|
| Device | M5StickC Plus 2 |
| MCU | ESP32 |
| Display | ST7789 135×240 LCD (landscape: 240×135) |
| IMU | MPU6886 6-axis accelerometer/gyroscope |
| PMIC | AXP2101 (battery management) |
| Communication | Bluetooth Low Energy (BLE 4.2) |

## Building

This is a [PlatformIO](https://platformio.org/) project targeting the Arduino framework.

```bash
# Build
~/.platformio/penv/bin/pio run

# Flash
~/.platformio/penv/bin/pio run -t upload

# Build + flash in one step
~/.platformio/penv/bin/pio run -t upload --upload-port /dev/ttyUSB0
```

Requires PlatformIO with the `espressif32@6.1.0` platform installed. The `m5stack/M5StickCPlus2` library (and its dependencies: M5Unified, M5GFX) is fetched automatically on first build.

## Screens

The **M5 front button** cycles through screens in order:

| # | Screen | Description |
|---|---|---|
| 0 | Clinometer | Bubble level with 1°/2°/3° rings, numeric X/Y tilt readout |
| 1 | Time | Current UTC time (HH:MM:SS) and date set by the Pi |
| 2 | RA/Dec | Right Ascension and Declination from the telescope |
| 3 | Alt/Az | Altitude and Azimuth from the telescope |
| 4 | Battery | Charge bar with colour coding, voltage (V) and level (%) |
| — | Message | Temporary full-screen overlay triggered by BLE command |

## Button behaviour

| Button | Short press | Long press (≥2 s) |
|---|---|---|
| M5 (front) | Cycle to next screen | — |
| Top (side) | Reboot | Power off (AXP192 shutdown) |
| Power (reserved) | — | — |

When a `SHOW_MSG_WAIT` message is active, pressing the M5 button (if it is in the watch list) sends a `EVENT BUTTON M5` notification over BLE instead of cycling screens.

---

## BLE Interface

### Connection parameters

| Parameter | Value |
|---|---|
| Device name | `M5-NexStar-Level` |
| Role | Peripheral / GATT server |
| MTU | 185 bytes (requested) |
| Default mode | Request / reply (no streaming unless enabled) |

The device advertises continuously. After a central disconnects, advertising restarts automatically.

### GATT service

**Service UUID:** `7d91b000-8f3b-4b63-b6a4-5d1e6b7a1000`

| Characteristic | UUID | Properties | Purpose |
|---|---|---|---|
| Command | `7d91b001-8f3b-4b63-b6a4-5d1e6b7a1000` | Write, Write Without Response | Pi → device: send a command |
| Response | `7d91b002-8f3b-4b63-b6a4-5d1e6b7a1000` | Read, Notify | Device → Pi: command replies and async events |
| Status | `7d91b003-8f3b-4b63-b6a4-5d1e6b7a1000` | Read | Compact device state snapshot (polled, no notify) |

### Protocol

Commands and responses are **ASCII text**, one per write/notify. Fields are space-separated.

**Newline framing (optional):** If a client sends commands that end with `\n` (or `\r\n`), the device detects this on the first such command and appends `\n` to every subsequent reply and async notification for that connection. This makes the stream appear as newline-delimited text to clients that treat BLE as a byte stream. Clients that send commands without a trailing `\n` receive plain responses with no terminator. The flag is sticky for the lifetime of a connection and resets on disconnect.

Subscribe to notifications on the **Response** characteristic to receive replies and asynchronous events (button presses, screen changes). The device sends one notify per command reply.

---

## BLE Commands

### `PING`

Returns a liveness acknowledgement.

```
→ PING
← OK PONG
```

---

### `GET_TILT`

Returns the current X (pitch) and Y (roll) tilt angles in decimal degrees.

```
→ GET_TILT
← TILT +0.42 -1.17
```

The sign convention follows the physical orientation of the device. Values update at ~15 Hz internally; the response reflects the most recent sample.

---

### `GET_STATUS`

Returns a one-line summary of device state.

```
→ GET_STATUS
← STATUS SCREEN=CLINOMETER BLE=1 STREAM=0 BAT=3.96 NIGHT=0
```

| Field | Values | Description |
|---|---|---|
| `SCREEN` | `CLINOMETER` `TIME` `RADEC` `ALTAZ` `BATTERY` `MESSAGE` | Active screen |
| `BLE` | `0` `1` | BLE connected flag |
| `STREAM` | `0` `1` | Tilt streaming enabled |
| `BAT` | float volts | Battery voltage (AXP2101) |
| `NIGHT` | `0` `1` | Night mode enabled |

---

### `GET_TIME`

Returns the current time as set by `SET_TIME`, ticking locally since then.

```
→ GET_TIME
← TIME 2026-04-19T18:42:10Z
```

Returns `TIME NONE` if time has not been set since boot.

---

### `GET_RADEC`

Returns the stored RA/Dec strings.

```
→ GET_RADEC
← RADEC 12:34:56 +07:08:09
```

Returns `--:--:--` placeholders until set by `SET_RADEC`.

---

### `GET_ALTAZ`

Returns the stored Alt/Az strings.

```
→ GET_ALTAZ
← ALTAZ +43.2 181.7
```

Returns `---` placeholders until set by `SET_ALTAZ`.

---

### `GET_MSG`

Returns the current message state.

```
→ GET_MSG
← MSG NONE

← MSG ACTIVE INF BUTTONS=M5 TEXT=Press M5 to continue
← MSG ACTIVE 4 BUTTONS=NONE TEXT=Moving altitude axis
```

The second field is the remaining lifetime in seconds, or `INF` for a persistent message.

---

### `SET_TIME <iso8601>`

Sets the device clock. The device ticks locally from this point.

```
→ SET_TIME 2026-04-19T18:42:10Z
← OK TIME
← ERR BAD_TIME
```

Format must be `YYYY-MM-DDTHH:MM:SSZ` (UTC, Z suffix required).

---

### `SET_RADEC <ra> <dec>`

Updates the RA/Dec values shown on the RA/Dec screen.

```
→ SET_RADEC 12:34:56 +07:08:09
← OK RADEC
← ERR BAD_ARGS
```

RA is `HH:MM:SS`. Dec is `+/-DD:MM:SS`. Values are stored as display strings; no range validation is performed.

---

### `SET_ALTAZ <alt> <az>`

Updates the Alt/Az values shown on the Alt/Az screen.

```
→ SET_ALTAZ +43.2 181.7
← OK ALTAZ
← ERR BAD_ARGS
```

Both values are decimal degrees. Values are stored as display strings.

---

### `SHOW_MSG <duration> <text>`

Displays a message on the full-screen message overlay.

```
→ SHOW_MSG 5 Moving altitude axis
→ SHOW_MSG INF Waiting for solar centering
← OK MSG
← ERR BAD_ARGS
```

| `<duration>` | Meaning |
|---|---|
| Integer (seconds) | Message auto-dismisses after this many seconds |
| `INF` | Message persists until `CANCEL_MSG` or a replacement |

The device switches to the message screen immediately and returns to the previous screen when the message expires or is cancelled. BLE and IMU continue running in the background.

---

### `SHOW_MSG_WAIT <duration> <buttons> <text>`

Displays a message and registers interest in one or more button presses. When a watched button is pressed, the device sends an `EVENT BUTTON <x>` notification.

```
→ SHOW_MSG_WAIT 30 M5 Press M5 when ready
→ SHOW_MSG_WAIT INF M5,A Confirm or abort
→ SHOW_MSG_WAIT 15 ANY Press any button to stop
← OK MSG_WAIT
← ERR BAD_ARGS
```

**Button mask values:**

| Value | Meaning |
|---|---|
| `M5` | Front M5 button |
| `A` | Top side button |
| `B` | Power/third button |
| `M5,A` | Comma-separated combination |
| `ANY` | Any of the three buttons |

The message remains visible after a button press until its timeout expires or `CANCEL_MSG` is received. Multiple button events can be generated if the user presses the button more than once.

---

### `CANCEL_MSG`

Dismisses the active message immediately and returns to the previous screen.

```
→ CANCEL_MSG
← OK MSG_CANCEL
```

Has no effect if no message is active (still returns `OK MSG_CANCEL`).

---

### `START_STREAM <period_ms>`

Enables periodic tilt notifications on the Response characteristic. The device sends a `TILT` line every `<period_ms>` milliseconds without waiting for a request.

```
→ START_STREAM 500
← OK STREAM 500
```

Minimum period is 100 ms. Streaming continues until `STOP_STREAM` or disconnection.

---

### `STOP_STREAM`

Disables tilt streaming.

```
→ STOP_STREAM
← OK STREAM 0
```

---

### `SET_NIGHT_MODE <on|off>`

Switches the display into night mode (or back to normal). In night mode all display colours are shifted to the red family to preserve dark-adapted vision at the telescope eyepiece. Elements that were previously green (1° clinometer ring, battery-good fill, BLE-connected indicator) are rendered in a warm orange-red to retain visual hierarchy; all other non-black colours use pure red.

```
→ SET_NIGHT_MODE ON
← OK NIGHT_MODE ON

→ SET_NIGHT_MODE OFF
← OK NIGHT_MODE OFF

← ERR BAD_ARGS   (if argument is missing or not ON/OFF)
```

Night mode persists until explicitly disabled or the device reboots. The current state is reported by `GET_STATUS` as `NIGHT=1` / `NIGHT=0`.

---

## Asynchronous Events

The device can send unsolicited notifications on the Response characteristic. Subscribe to notifications to receive them.

### Screen change events

Sent whenever the active screen changes (button press, message activation/expiry, or BLE command). Clients can use this to pause or resume periodic `SET_RADEC` / `SET_ALTAZ` updates when those screens are not visible.

```
EVENT SCREEN CLINOMETER
EVENT SCREEN TIME
EVENT SCREEN RADEC
EVENT SCREEN ALTAZ
EVENT SCREEN BATTERY
EVENT SCREEN MESSAGE
```

### Button events

Sent when a button is pressed that is listed in the current `SHOW_MSG_WAIT` button mask.

```
EVENT BUTTON M5
EVENT BUTTON A
EVENT BUTTON B
```

### Streaming tilt

When `START_STREAM` is active, periodic tilt notifications are sent in the same format as `GET_TILT`:

```
TILT +0.38 -1.12
```

---

## Error responses

| Response | Meaning |
|---|---|
| `ERR UNKNOWN_COMMAND` | Command token not recognised |
| `ERR BAD_ARGS` | Wrong number or format of arguments |
| `ERR BAD_TIME` | `SET_TIME` value could not be parsed |

---

## Status characteristic

The Status characteristic (`7d91b003-...`) is a read-only snapshot updated every ~2 seconds. It does not issue notifications; poll it when needed.

```
SCREEN=CLINOMETER;BLE=1;BAT=3.96;STREAM=0
```

---

## Python tools

Dependencies are managed with [uv](https://docs.astral.sh/uv/). From the project root:

```bash
uv sync          # create .venv with all dependencies
uv sync --group dev   # include pytest / pytest-asyncio for running tests
```

### tools/m5ctl

`tools/m5ctl` is a Python 3 command-line client for the BLE interface.

```
usage: m5ctl [-h] [-d ADDR] [-t SEC] COMMAND ...

options:
  -d ADDR   BLE address (default: F0:24:F9:9B:E2:52)
  -t SEC    seconds to wait for a response (default: 5)
```

| Command | Arguments | Description |
|---|---|---|
| `ping` | | Ping the device |
| `tilt` | | Get current X/Y tilt angles |
| `status` | | Get device status (screen, BLE, battery, stream, night mode) |
| `get-time` | | Get current device time |
| `get-radec` | | Get stored RA/Dec values |
| `get-altaz` | | Get stored Alt/Az values |
| `get-msg` | | Get current message state |
| `set-time` | `<iso8601>` | Set device clock from UTC ISO-8601 string |
| `set-radec` | `<ra> <dec>` | Set RA/Dec display values |
| `set-altaz` | `<alt> <az>` | Set Alt/Az display values |
| `show-msg` | `<seconds\|inf> <text>` | Display a timed or persistent message |
| `show-msg-wait` | `<seconds\|inf> <buttons> <text>` | Display a message and watch for a button press |
| `cancel-msg` | | Cancel the active message immediately |
| `stream` | `<period_ms>` | Enable periodic tilt notifications |
| `stop-stream` | | Disable tilt streaming |
| `night-mode` | `on\|off` | Enable or disable red-only night mode |
| `listen` | | Print all BLE notifications (Ctrl+C to stop) |
| `scan` | | Scan for nearby BLE devices |

Examples:

```bash
uv run tools/m5ctl tilt
uv run tools/m5ctl status
uv run tools/m5ctl set-time "2026-05-04T21:00:00Z"
uv run tools/m5ctl set-radec "12:34:56" "+07:08:09"
uv run tools/m5ctl night-mode on
uv run tools/m5ctl stream 500
uv run tools/m5ctl listen
```

### tools/set-utc-now

Bash wrapper that reads the current UTC clock, adds a small latency offset, and calls `m5ctl set-time` in one step:

```bash
uv run tools/set-utc-now
```

---

## Test suite

`tests/` contains a pytest suite that exercises the full BLE command interface against a real device, including the dynamic newline-framing protocol.

```bash
# Run all tests (device must be on and reachable)
uv run pytest

# Specify a non-default BLE address
uv run pytest --device AA:BB:CC:DD:EE:FF

# Run only the newline protocol tests
uv run pytest tests/test_newline.py
```

Set the environment variable `M5_ADDR` as an alternative to `--device`.

---

## Project structure

```
├── platformio.ini         Build configuration (espressif32@6.1.0, m5stick-c)
├── pyproject.toml         Python dependencies and pytest config (managed by uv)
├── src/
│   ├── main.cpp           Arduino setup/loop — orchestrates all subsystems
│   ├── model/
│   │   └── DeviceState.h  Shared state struct accessed by all modules
│   ├── imu/
│   │   ├── ImuManager.h
│   │   └── ImuManager.cpp Tilt sampling at ~15 Hz, exponential low-pass filter
│   ├── ble/
│   │   ├── BleManager.h
│   │   └── BleManager.cpp GATT server, command parser, response/event notify
│   ├── ui/
│   │   ├── Display.h
│   │   └── Display.cpp    All six screen renderers (sprite-buffered via M5GFX)
│   └── system/
│       ├── PowerManager.h/.cpp  M5StickCPlus2 init, battery voltage/level, power-off
│       └── Buttons.h/.cpp       Button polling, screen cycle, reboot/sleep
├── tools/
│   ├── m5ctl              Python 3 BLE command-line client
│   └── set-utc-now        Bash helper: set device clock to current UTC
├── tests/
│   ├── conftest.py        BleSession helper and pytest fixtures
│   ├── test_commands.py   BLE command interface tests
│   └── test_newline.py    Newline-framing protocol tests
└── docs/
    └── m5stickc-clinometer-ble-spec.md   Full design specification
```

## Architecture notes

- The BLE stack runs on its own FreeRTOS task (managed by the ESP32 Arduino BLE library). All other work runs in the Arduino `loop()` task.
- BLE callbacks write commands into a volatile hand-off buffer (`pendingBleResponse`); the main loop drains this buffer each tick and issues the BLE notify. This keeps all M5 hardware access (IMU, display, power) exclusively on the main loop task.
- Hardware is initialised through `M5StickCPlus2.h` / M5Unified; the display uses M5GFX sprite double-buffering for flicker-free rendering.
- All timing uses non-blocking `millis()` gates — no `delay()` except the mandatory 1 ms yield at the end of each loop tick.
- Flash usage: ~40% of 3 MB. RAM usage: ~13% of 320 KB.

# Know-How: M5StickC BLE Clinometer

Practical lessons learned while building this project. Not a changelog, README, or ADR log.
Each section follows the pattern: **problem or question → solution → why it matters**.

## Scope

**This document captures:**
- Subtle bugs and their root causes
- Hardware-specific behavior and platform quirks
- Library and vendor stack limitations
- Design patterns that proved useful in practice
- Non-obvious decisions worth carrying forward to similar projects

**It does not replace:**
- `README.md` — user-facing installation and usage documentation
- `CHANGELOG.md` — release history and version notes
- `docs/adr/` — major architecture decision records
- Issue tracking — pending bugs and feature requests

## How AI agents should use this document

Read this document before making architectural changes, porting to a new M5Stack board,
modifying the IMU math, changing BLE behavior, or reorganizing the build system.
The lessons here represent debugging history that is not fully visible in the code or
git log alone.

Prefer preserving the patterns captured here unless there is a clear reason to supersede
them. If a lesson becomes obsolete, do not delete it silently — mark it:

> Status: Superseded as of vX.Y — [brief reason]

---

## Contents

1. [Multi-platform M5Stack Support via M5Unified](#1-multi-platform-m5stack-support-via-m5unified)
2. [BLE on ESP32: Deferred Command Processing](#2-ble-on-esp32-deferred-command-processing)
3. [GATT Service Design and Text Protocol](#3-gatt-service-design-and-text-protocol)
4. [IMU Math: Coordinate Frames and Angle Convention](#4-imu-math-coordinate-frames-and-angle-convention)
5. [NVS Persistence Patterns](#5-nvs-persistence-patterns)
6. [Non-blocking Audio: Melody Sequencer](#6-non-blocking-audio-melody-sequencer)
7. [Display Dirty-Check Optimization](#7-display-dirty-check-optimization)
8. [Python BLE Client Patterns (Bleak)](#8-python-ble-client-patterns-bleak)
9. [Real-time 3D Visualization: OpenGL + Async BLE](#9-real-time-3d-visualization-opengl--async-ble)
10. [Build and Version Management](#10-build-and-version-management)

---

## 1. Multi-platform M5Stack Support via M5Unified

### Use M5Unified as the hardware abstraction layer

M5Unified provides a single API for display, IMU, buttons, speaker, and power management
across the entire M5Stack family (StickC Plus 2, StickS3, Core2, CoreS3, Grey).
Without it, each board needs separate `#ifdef` chains for every peripheral call.
The tradeoff is that M5Unified is a large dependency and adds binary size,
but for any project targeting more than one M5Stack board it is the correct choice.

### PlatformIO environment per board

Each board gets its own `[env:...]` block in `platformio.ini`. Keep the common flags in
`[env]` and override only what differs:

```ini
[env]
platform = espressif32@^7.0.1
framework = arduino
board_build.partitions = huge_app.csv
lib_deps = m5stack/M5Unified

[env:m5stickc-plus2]
board = m5stick-c

[env:mstickS3]
board = esp32-s3-devkitc-1
board_build.arduino.partitions = default_8MB.csv
board_build.arduino.memory_type = qio_opi
build_flags =
    -DESP32S3
    -DBOARD_HAS_PSRAM
    -mfix-esp32-psram-cache-issue
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DARDUINO_USB_MODE=1
```

Use `#ifdef ESP32S3` in firmware only for the very few places where the libraries behave
differently — not for peripheral access, which M5Unified already normalizes.

### M5StickS3: PSRAM, partitions, and USB serial

M5StickS3 uses the ESP32-S3 chip with octal PSRAM. Three things are required:

- `board_build.arduino.memory_type = qio_opi` — selects octal SPI for PSRAM
- `-mfix-esp32-psram-cache-issue` — compiler workaround for S3 cache errata
- `default_8MB.csv` partition table — the default 4 MB layout does not fit

The S3 also uses USB CDC for serial, not UART. Without
`-DARDUINO_USB_CDC_ON_BOOT=1 -DARDUINO_USB_MODE=1` the serial monitor is silent.

### M5StickS3: BTC task stack overflow

The Bluetooth Controller (BTC) task on the S3 uses a hardcoded stack of 3584 bytes
in the prebuilt `libbt.a`. Complex BLE operations — particularly during connection
negotiation — can overflow this stack and cause a reset.

Fix: add to `build_flags`:
```
-DCONFIG_BT_BTC_TASK_STACK_SIZE=10240
```

This increases the stack size for the BTC task and eliminates the hang that occurs
when a client connects and immediately sends a long command.

### Boards without an RTC (M5StickS3 and M5Stack Grey)

These boards have no onboard RTC. When power is removed, wall-clock time is lost.
Design your application to re-send time after every boot:
the host app or setup script should issue `SET_TIME` as part of its startup sequence.
Document this clearly — users connecting to a freshly-rebooted device will see
"NONE" on the time screen until time is set.

**Applies to:** ESP32, M5Stack, Arduino, PlatformIO, M5Unified, multi-board embedded projects

---

## 2. BLE on ESP32: Deferred Command Processing

### Problem: complex logic inside `onWrite()` triggers WDT resets

On M5StickS3 (and to a lesser degree other ESP32 variants), the Bluedroid BLE stack
runs `BLECharacteristicCallbacks::onWrite()` inside a FreeRTOS task with a small stack
and a watchdog timer. Any complex work done there — string parsing, NVS access,
display updates — risks a watchdog timeout and reboot.

### Solution: copy-and-defer

`onWrite()` does only the minimum: copy the incoming bytes and set a flag.

```cpp
void onWrite(BLECharacteristic* pChar) override {
    auto val = pChar->getValue();
    size_t copyLen = min(val.size(), sizeof(s_state->pendingBleCommand) - 1);
    memcpy((char*)s_state->pendingBleCommand, val.data(), copyLen);
    s_state->pendingBleCommand[copyLen] = '\0';
    s_state->pendingBleCommandReady = true;
}
```

`BleManager::update()`, called from the main Arduino loop, checks the flag and runs
`processCommand()`. This keeps all business logic on the main task where the watchdog
does not apply.

### Problem: large local buffers overflow the Arduino task stack on S3

Even with deferred processing, large `char cmd[256]` and `char resp[160]` declared as
local variables in `processCommand()` can overflow the Arduino task stack on S3
(the stack is smaller than on the StickC Plus 2).

### Solution: static buffers inside the function

```cpp
static void processCommand(const char* raw) {
    static char cmd[256];
    static char resp[160];
    // ...
}
```

`static` local variables live in BSS (data segment), not the stack. The function is
only ever called from one task (main), so there is no re-entrancy concern.

### Bluedroid TX notification queue limit

The Bluedroid stack's BLE TX notification queue holds at most **31 items**.
Sending more than 31 notifications without yielding drops packets silently.

For multi-line streaming responses (like `HELP`), send one line per main-loop tick:

```cpp
if (state.pendingBleHelpLine >= 0) {
    // send next help line and increment counter
    // on last line, reset to -1
}
```

This makes the main loop the rate-limiter for notification output.

**Applies to:** ESP32, Bluedroid BLE stack, Arduino, FreeRTOS, M5StickS3, any ESP32 BLE peripheral

---

## 3. GATT Service Design and Text Protocol

### Three-characteristic layout

```
Service UUID: 7d91b000-8f3b-4b63-b6a4-5d1e6b7a1000

CMD    (b001): WRITE-only   — client sends commands
RESP   (b002): READ/NOTIFY  — firmware sends responses and async events
STATUS (b003): READ-only    — firmware writes a semicolon-delimited status string every ~2s
```

`STATUS` exists specifically so a client can poll device state without subscribing to
notifications. This matters for simple integrations (scripts, shell one-liners) that
only need to know whether BLE is connected or streaming is active.
Keep `RESP` and `STATUS` separate — if you put async events and status on the same
characteristic, clients that only care about responses must filter noise on every read.

### Text protocol over BLE

A text-based request/response protocol (`PING → OK PONG`, `GET_TILT → TILT 1.2 0.5 0.98`)
is the right default for a peripheral with a companion app:

- Any BLE scanner (nRF Connect, BLE Terminal) can debug it without custom tooling
- Command parsing is trivial (`strtok`, `sscanf`, `strcmp`)
- New commands are additive and backward-compatible
- Error responses are human-readable (`ERR BAD_ARGS`, `ERR UNKNOWN_COMMAND`)

Binary protocols are faster and more compact, but the savings are rarely worth the
debugging cost at the bandwidth rates BLE provides.

### Newline-optional protocol

Some clients (Python scripts using `\n`-framed reads) need a trailing newline.
Others (raw BLE tools) do not want one. Rather than hardcoding either:

- Detect whether the client's **first write** ends with `\n`
- If yes, append `\n` to all subsequent responses and notifications
- The flag resets on reconnect, so different clients can coexist

```cpp
if (!state.bleClientWantsNewline && val.back() == '\n') {
    state.bleClientWantsNewline = true;
}
```

### Input sanitization

BLE commands can arrive from any platform. Common problems:

| Input problem | Fix |
|---|---|
| UTF-8 NBSP `\xC2\xA0` (copy-paste from web docs) | Replace with ASCII space before parsing |
| Ideographic space `\xE3\x80\x80` (Japanese IME) | Replace with ASCII space |
| ASCII control chars `0x00–0x1F`, `0x7F` | Reject with `ERR INVALID_CHAR U+XXXX` |
| Trailing `\r\n` or `\n` | Strip before further processing |

Doing this in one pass before `strtok` keeps the parser simple.

**Applies to:** ESP32, BLE GATT peripherals, embedded text protocols, IoT devices with companion apps

---

## 4. IMU Math: Coordinate Frames and Angle Convention

### The core problem: each device has different IMU orientation

On M5StickC Plus 2 (landscape), the physical IMU chip is rotated 90° relative to the
screen. On M5Stack Core2 (square), the IMU frame roughly aligns with the screen.
On M5StickS3, both X and Y are negated relative to the Plus 2.

If you report raw IMU axes directly, the same physical orientation produces different
numbers on each device. Users — and tests — cannot reason about the device abstractly.

### Solution: define a UX frame and map to it per device

The **UX frame** is defined by the screen:

```
UX +X = screen right
UX +Y = screen up
UX +Z = out of screen (toward viewer)
```

Each device has a one-time mapping from IMU axes to UX axes:

| Device | UX +X | UX +Y | UX +Z |
|---|---|---|---|
| M5StickC Plus / Plus 2 | IMU +Y | IMU −X | IMU +Z |
| M5Stack Core2 / CoreS3 / Grey | IMU +X | IMU +Y | IMU +Z |
| M5StickS3 | IMU −X | IMU −Y | IMU +Z |

After mapping, all angle computation uses the UX frame exclusively.

### Consistent angle sign convention

```
reported_pitch = + rotation about UX +X   (top of screen rises = positive)
reported_roll  = − rotation about UX +Y   (right side of screen rises = positive)
```

This convention is astronomy-friendly: when the device is mounted with its right side
pointing toward a telescope aperture, positive roll means the aperture rises, which
corresponds to increasing altitude. Documenting the sign convention explicitly prevents
sign-flip bugs when porting to new mounts.

### Cross-axis atan2 for stable readings

Do not use `asin(gux)` for pitch — it becomes numerically unstable when the device is
also rolled. Use cross-axis atan2:

```cpp
float uxPitchDeg = atan2f(gux, sqrtf(guy*guy + guz*guz)) * RAD_TO_DEG;
float uxRollDeg  = atan2f(guy, sqrtf(gux*gux + guz*guz)) * RAD_TO_DEG;
```

Both readings remain stable through any single-axis or combined tilt because the
denominator is always the projection onto the plane perpendicular to the axis being measured.

### Handle the upside-down case

When the device is tilted past vertical, `guz` goes negative. At that point, the
angle math would wrap incorrectly. Fix: flip the sign of the sqrt term based on `guz`:

```cpp
float s = (guz < 0.0f ? -1.0f : 1.0f);
uxPitchDeg = atan2f(gux, s * sqrtf(guy*guy + guz*guz)) * RAD_TO_DEG;
```

This ensures readings remain continuous through the full ±180° range.

### Rodrigues rotation for gravity calibration

When the user places the device on a known-level surface and triggers `CALIBRATE`,
store a 3×3 rotation matrix that maps the measured gravity vector to `(0, 0, 1)`.
Apply this matrix to all subsequent IMU readings before any angle computation.

Use Rodrigues' rotation formula rather than Euler angles:

```
k     = cross(g_ref, ẑ) / |cross(g_ref, ẑ)|   (rotation axis)
sinθ  = |cross(g_ref, ẑ)|
cosθ  = g_ref · ẑ = gz
R     = cosθ · I + (1 − cosθ) · k⊗kᵀ + sinθ · K
```

where `K` is the skew-symmetric matrix of `k`.
Store `R` (9 floats) in NVS as `cal_gx`, `cal_gy`, `cal_gz` (the reference vector —
reconstruct `R` at load time). Rodrigues avoids gimbal lock and is well-defined
for any rotation angle except exact anti-parallel vectors (device held upside-down
at calibration time — handle that edge case explicitly).

### Configurable pitch/roll axes

For unusual telescope mounts (device rotated 90°, mounted sideways), expose axis
remapping as a BLE command (`SET_PITCHROLL +Y,+X`) and store the axis codes in NVS.
This lets users adapt the readout to their physical mounting without reflashing.
Axis codes: `±1` = `±X`, `±2` = `±Y`.

**Applies to:** IMU/accelerometer projects, multi-board angle measurement, astronomy tools, any device with physical orientation constraints

---

## 5. NVS Persistence Patterns

### Never auto-write NVS on each BLE command

ESP32 NVS (Non-Volatile Storage) sits in flash. Flash has a finite write endurance.
More importantly, NVS writes are slow relative to BLE response latency.
Avoid writing on every `SET_TIME`, `SET_RADEC`, or similar command.

Instead, expose an explicit `PERSIST` command. The user or automation script decides
when state is worth committing to flash.

### Atomic commit via a validity byte

Write all NVS keys in order, then write a `valid=1` byte **last**.
On load, check `valid` first — if it is not `1`, discard the stored data.

If power is lost partway through a write, the `valid` byte will still be `0` (or stale),
and the firmware starts with defaults rather than partially-written values.

```cpp
// Save
nvs.putUChar("valid", 0);          // invalidate first
nvs.putString("tz", label);
nvs.putInt("tz_offset", offsetSec);
nvs.putFloat("cal_gx", calVec[0]);
// ... all other keys ...
nvs.putUChar("valid", 1);          // commit last
```

### Invalidate without erasing

`PERSIST CLEAR` writes only `valid=0` — a single flash write that invalidates the
stored config. The underlying data remains untouched. This enables `PERSIST RESTORE`
to bring it back if the user changed their mind.

This pattern — invalidate by flipping a flag, recover without re-entering all values —
is more user-friendly than a hard factory-reset that erases everything irreversibly.

### NVS namespace limit

ESP-IDF NVS namespace names are limited to **15 characters** (and in practice, short names
are safer). Use a compact, project-specific string like `"clino"`. NVS key names are also
limited to 15 characters — keep key names descriptive but short (`"tz_offset"`, `"cal_gx"`).

**Applies to:** ESP32, ESP-IDF NVS, flash persistence on microcontrollers, any embedded device with user-configurable settings

---

## 6. Non-blocking Audio: Melody Sequencer

### Do not block the main loop with `delay()` for audio

Calling `tone(freq, duration)` or `delay(ms)` between notes blocks the entire main loop:
BLE events stop being processed, the display freezes, and button presses are dropped.
On M5Stack this is especially visible — the BLE connection can drop during a multi-note
sequence played synchronously.

### Pattern: pre-computed note queue + main-loop tick function

1. On `BEEP` command, parse the note string into a `MelodyNote[32]` array of
   `{uint16_t freqHz, uint16_t durMs}` pairs and set `melodyLength`.
2. In the main loop, call `tickMelody()` every iteration:

```cpp
static void tickMelody(DeviceState& state) {
    if (state.melodyLength == 0) return;
    uint32_t now = millis();
    if (now >= state.melodyNoteUntilMs) {
        MelodyNote& note = state.melodyNotes[state.melodyPos];
        if (note.freqHz > 0) M5.Speaker.tone(note.freqHz, note.durMs);
        else                  M5.Speaker.stop();
        state.melodyNoteUntilMs = now + note.durMs;
        state.melodyPos++;
        if (state.melodyPos >= state.melodyLength) state.melodyLength = 0;
    }
}
```

The BLE loop, display update, and button polling all continue normally between notes.

### Musical notation parser

A readable notation format is worth the parser complexity for user-facing beep commands.
Notation used here:

```
C D E F G A B         — natural notes, default octave 5
C# Db                 — sharps and flats
'  ,                  — octave up / down (can stack: C'' = C7)
1–9                   — override note duration (units = one beat)
.                     — dotted note (×1.5 duration)
-                     — rest
```

Default tempo: 120 BPM (one quarter note = 500 ms).
Example: `"C4 D E. F4. G A B' C''"` plays a C-major scale with the last four notes
doubled in duration, dotted fourth and fifth, ending two octaves up.

**Applies to:** Arduino/ESP32 main-loop architecture, M5Stack speaker, any cooperative real-time loop that must not block

---

## 7. Display Dirty-Check Optimization

### Problem: SPI DMA writes dominate CPU budget when idle

On ESP32, pushing a full framebuffer over SPI DMA is relatively expensive. When the
device is stationary (on a tripod), the screen content never changes — yet without
a dirty check, the firmware redraws every loop iteration, burning cycles that
Bluedroid needs for BLE event processing.

### Solution: skip redraw when state is unchanged

Compare the fields that affect the current screen against their previous values.
Only call `g_display.update()` when something changed:

```cpp
bool dirty =
    fabsf(state.pitchDeg - prev.pitchDeg) > 0.05f ||
    fabsf(state.rollDeg  - prev.rollDeg)  > 0.05f ||
    state.battLevel != prev.battLevel               ||
    state.bleConnected != prev.bleConnected          ||
    state.nightMode != prev.nightMode;

if (dirty) {
    g_display.update(state);
    prev = state;
}
```

A threshold of 0.05° prevents flickering from ADC noise while still being well below
the display's angular resolution. The result is measurable: BLE latency drops visibly
on stationary setups.

### Auto-dim backlight

Drop the backlight to a low level after N seconds of inactivity (no BLE command
received AND no significant tilt change). Restore to full brightness immediately on
the next BLE command or large tilt event.

Inactivity thresholds used here: 60 seconds, tilt change < 5° per second.
Night mode overrides the auto-dim brightness floor to stay dark.

**Applies to:** ESP32, SPI display, M5Stack, any embedded UI where CPU budget is shared with a radio stack

---

## 8. Python BLE Client Patterns (Bleak)

### Platform-specific reconnection strategies

Bleak's connection behavior differs significantly across platforms:

**Windows (WinRT):**
After a device disconnects, the WinRT BLE stack may not immediately re-advertise the
device in the OS cache. A plain `BleakClient.connect()` call fails silently.
Fix: run `BleakScanner.find_device_by_address()` first to force a fresh scan,
then pass the discovered `BLEDevice` to `BleakClient`:

```python
if sys.platform == "win32":
    device = await BleakScanner.find_device_by_address(addr, timeout=5.0)
    client = BleakClient(device)
else:
    client = BleakClient(addr, dangerous_use_bleak_cache=True)
```

**Linux (BlueZ):**
`dangerous_use_bleak_cache=True` tells Bleak to reuse BlueZ's D-Bus cached object path
for the device rather than re-discovering it. On fast reconnects this is usually valid
and avoids a 5-second scan timeout.

**Notification subscription timing:**
On Windows, subscribing to notifications immediately after `connect()` sometimes fails.
A 100ms delay before `start_notify()` avoids this race.

### Command batching over a single connection

BLE connection setup takes 0.5–3 seconds depending on platform.
For a script that sends many commands (setup scripts, test suites), reconnecting per
command is prohibitively slow. Batch commands:

```python
async def cmd_exec(self, commands: list[str]) -> list[str]:
    async with self._connect() as client:
        results = []
        for cmd in commands:
            await client.write_gatt_char(CMD_UUID, cmd.encode())
            response = await self._recv_response(client)
            results.append(response)
        return results
```

For test suites, share a single connection across an entire test module
(`--ble-keep-alive` mode). The session fixture handles flush/resync between tests
instead of reconnecting.

### Test isolation: flush before each test

BLE is stateful. A previous test may have left a stream running or a message displayed.
Before each test, send `STOP_STREAM` followed by `PING`, then drain the notification
queue until `"OK PONG"` arrives:

```python
async def flush(self):
    await self.send("STOP_STREAM")
    await self.send("CANCEL_MSG")
    response = ""
    while response != "OK PONG":
        await self.send_raw("PING")
        response = await self.recv(timeout=2.0)
```

This is cheaper than reconnecting and catches race conditions where a stream packet
arrives after `STOP_STREAM` is acknowledged.

### Skip async EVENT notifications

The firmware sends unsolicited `EVENT ...` notifications when internal state changes
(e.g., `EVENT SCREEN CLINOMETER` when a message overlay dismisses).
In `send()`, skip EVENT lines and keep waiting for the expected response:

```python
async def send(self, cmd: str, timeout: float = 5.0) -> str:
    await self._write(cmd)
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        response = await self._recv(timeout=deadline - asyncio.get_event_loop().time())
        if not response.startswith("EVENT "):
            return response
```

Without this, tests that trigger screen changes fail intermittently.

### Timezone: abbreviation map separate from IANA

Timezone abbreviations are ambiguous (`EST` is UTC−5 in the US but UTC+11 in Australia).
Keep a hardcoded map of unambiguous abbreviations:

```python
_TZ_FIXED_OFFSETS = {
    "UTC": "+00:00", "GMT": "+00:00",
    "CET": "+01:00", "JST": "+09:00",
    "EST": "-05:00", "CST": "-06:00", "MST": "-07:00", "PST": "-08:00",
    # etc.
}
```

For unknown strings, fall back to IANA `ZoneInfo` lookup. The fixed map ensures that
`CET` always means `+01:00` regardless of DST state — which is what firmware users
who type `CET` expect.

### Argparse collision with negative UTC offsets

`-05:00` looks like a flag to argparse. Before parsing, rewrite any argument that matches
a UTC offset pattern to use `~` as the sign:

```python
sys.argv = [
    "~" + a[1:] if re.match(r'^-\d\d:\d\d$', a) else a
    for a in sys.argv
]
```

Then translate `~` back to `-` before sending to firmware. This is simpler than using
`nargs='?'` with custom `type=` handlers across every subcommand that accepts a timezone.

**Applies to:** Python, Bleak BLE library, Windows/Linux BLE, asyncio, pytest integration testing against real hardware

---

## 9. Real-time 3D Visualization: OpenGL + Async BLE

### Thread architecture: async BLE in daemon thread, OpenGL on main thread

OpenGL (via PyOpenGL) and most windowing toolkits (Pygame, GLUT) require the main thread.
Bleak is async. The solution:

1. Start a daemon thread that creates its own `asyncio` event loop and runs the BLE client
2. Publish tilt state via a `threading.Lock`-protected dataclass
3. Main thread renders at ~60 FPS, reading from the shared state

```python
@dataclass
class TiltState:
    pitch: float = 0.0
    roll: float = 0.0
    acc_mag: float = 1.0
    lock: threading.Lock = field(default_factory=threading.Lock)

def ble_worker(state: TiltState):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_ble_loop(state))
```

The daemon thread reconnects automatically on BLE drops without interrupting rendering.

### Reconstruct the gravity vector from pitch and roll

Firmware sends two angles. The visualizer needs a 3D gravity vector to orient the model:

```python
sin_p = math.sin(math.radians(pitch))
sin_r = math.sin(math.radians(roll))
cos_sq = max(0.0, 1.0 - sin_p**2 - sin_r**2)
guz = math.sqrt(cos_sq)
if pitch_beyond_90 or roll_beyond_90:
    guz = -guz   # device past vertical
gux = sin_r      # or sin_p depending on axis mapping
guy = sin_p      # ditto
```

The firmware reports `guz < 0` via the `accMag` sign when the device is upside-down
(angles > 90°); use this to select the correct branch without sending extra data.

### Quaternion rotation: avoid Euler singularities

Convert the gravity vector directly to a device orientation quaternion using the
shortest-arc rotation from the current gravity direction to `(0, 0, 1)`:

```python
def quat_from_vecs(v_from, v_to):
    k = np.cross(v_from, v_to)
    k_len = np.linalg.norm(k)
    if k_len < 1e-9:                         # parallel or anti-parallel
        return (1, 0, 0, 0) if v_from @ v_to > 0 else (0, 1, 0, 0)
    k /= k_len
    cos_a = np.clip(v_from @ v_to, -1.0, 1.0)
    sin_a = k_len
    return (cos_a, *sin_a * k)               # (w, x, y, z)
```

This sidesteps Euler angle gimbal lock entirely. Apply the quaternion to OpenGL via
`glRotatef` + axis-angle conversion, or via a rotation matrix built from the quaternion.

### Device model auto-detection via GET_BOARD

Query `GET_BOARD` at startup and look up a device model record from a dictionary:

```python
BOARD_TO_MODEL = {
    "M5StickCPlus2": MODEL_STICKC,
    "M5StickS3":     MODEL_STICKS3,
    "Core2":         MODEL_CORE2,
    "CoreS3":        MODEL_CORES3,
}
```

Each model record specifies physical dimensions, camera position, IMU-to-UX axis mapping,
and screen face geometry. Storing these as data rather than conditionals keeps the
rendering code clean and makes adding a new board a one-line change.

### GLUT bitmap fonts as fallback for Python 3.15+

`pygame.font` and `pygame.freetype` have a circular import bug in Python 3.15 that
raises an `ImportError` at startup. Use GLUT bitmap fonts for HUD text and degrade
gracefully:

```python
try:
    from OpenGL.GLUT import glutBitmapCharacter, GLUT_BITMAP_HELVETICA_18
    _GLUT_AVAILABLE = True
except ImportError:
    _GLUT_AVAILABLE = False

def draw_text(x, y, text):
    if not _GLUT_AVAILABLE:
        return
    # ... glutBitmapCharacter loop
```

GLUT bitmap fonts are rasterized and do not require a font file, making them a reliable
fallback when `pygame.font` is unavailable.

**Applies to:** Python 3D visualization, PyOpenGL, Pygame, asyncio + threading patterns, any GUI app that consumes a live BLE stream

---

## 10. Build and Version Management

### Pre-commit hook stamps firmware version

Hardcoded version strings drift out of sync with git history.
Use a pre-commit hook to auto-write `src/version.h` before each commit:

```sh
#!/bin/sh
# scripts/pre-commit
MAJOR=1
MINOR=1
COMMITS=$(git rev-list --count HEAD)
echo "#define FW_VERSION \"${MAJOR}.${MINOR}.${COMMITS}\"" > src/version.h
git add src/version.h
```

Install with `scripts/install-hooks`. The firmware displays the version on a SYSINFO
screen and reports it in `GET_STATUS`, giving users and the developer a precise way to
identify what is running on the device.

### `huge_app.csv` partition table for Arduino + BLE

The default ESP32 Arduino partition table allocates ~1.2 MB for the app.
A full Arduino sketch with M5Unified and Bluedroid exceeds this.
Always use `board_build.partitions = huge_app.csv` (ships with arduino-esp32):
it allocates ~3 MB for the app and leaves space for NVS and OTA.

### `uv` for Python dependency management

Use `uv` to manage the Python venv and dependencies:

```
uv run pytest                   # run tests in the managed venv
uv run tools/m5ctl ping         # run the CLI tool
uv add bleak                    # add a dependency to pyproject.toml
```

Plain `python` or `python3` are not necessarily on PATH and do not have `bleak` or
`tzdata` installed globally. Always use `uv run` in documentation, CI, and scripts.
Lock the dependency graph with `uv lock` and commit `uv.lock` so builds are reproducible.

### Q40 fixed-point arithmetic for sidereal time

Sidereal time advances at a rate of 1.0027379... solar days per day.
Floating-point accumulation over hours introduces drift. Use a Q40 fixed-point counter:

```cpp
// Rate: 2^40 × 1.0027379... / 86400 ≈ 12760671 counts per second
const uint64_t SIDEREAL_INC_Q40 = 12760671ULL;

// Tick every second:
state.lstPhaseQ40 = (state.lstPhaseQ40 + SIDEREAL_INC_Q40) & ((1ULL<<40)-1);

// Read LST in seconds:
uint32_t lstSec = (uint32_t)(state.lstPhaseQ40 >> 40) % 86400;
```

The counter rolls over cleanly at 2^40 counts (= one sidereal day), and the integer
arithmetic is exact on ESP32. Reconstruct the initial phase from UTC + longitude at
load time using the linear GMST formula (error < 0.006 s at year 2100).

**Applies to:** PlatformIO, ESP32, Arduino BLE firmware, Python uv toolchain, git hooks for embedded version stamping, sidereal/astronomical time on microcontrollers

---

## Maintenance

Edit for clarity, merge redundant lessons, and add new entries freely.
Do not silently delete lessons that become obsolete — mark them instead:

> Status: Superseded as of vX.Y — [brief reason]

This preserves the debugging history even after the underlying fix is in place.

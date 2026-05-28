# M5StickC Plus 2 Bluetooth Clinometer

A BLE-enabled clinometer and telescope status display for the M5StickC Plus 2 (ESP32). Used to align a NexStar Alt/Az GoTo telescope mount and display live coordinates sent from a Raspberry Pi.

![Bubble Level](docs/images/clinometer_bubble.png)

![Date/Time](docs/images/clinometer_datetime.png)

![RA Dec](docs/images/clinometer_radec.png)

![Alt Az](docs/images/clinometer_altaz.png)

![Battery](docs/images/clinometer_battery.png)

## What it does

- Shows a live **bubble level** (clinometer) based on the built-in IMU — used to level the telescope mount
- Displays **time**, **RA/Dec**, and **Alt/Az** coordinates pushed from the Raspberry Pi over BLE
- Exposes a **BLE GATT service** so a Raspberry Pi can query tilt angles and update the displayed data at any time, regardless of which screen is active
- Supports **operator messages** — the Pi can push short text to the display, optionally waiting for a button acknowledgement
- Supports **night mode** — switches all display colours to red/orange-red to preserve dark-adapted vision at the eyepiece
- **Auto-rotates the display 180°** when that orientation would put the screen's top edge closer to physical up — all screens flip together, with ±0.3 g hysteresis to prevent flickering near vertical
- **Plays a brief startup tone** on boot (single 3600 Hz beep) to confirm speaker initialisation; volume is tuned per board family (lower for louder models such as the M5Stack)
- **Persists settings across power cycles** — the RTC always stores true UTC and is restored automatically on every boot. The timezone label, UTC offset, observer longitude, and calibration reference vector can additionally be saved to on-chip NVM with an explicit `PERSIST` command; on the next boot the device restores all of these without any BLE interaction. `PERSIST CLEAR` invalidates stored settings with a single flash write; `PERSIST RESTORE` re-applies stored settings to the running device without a reboot. On devices without an onboard RTC (e.g. M5Stack Grey) the clock is not preserved across power cycles; `SET_TIME` must be re-sent after each reboot

## Hardware

| Item | Detail |
|---|---|
| Reference device | M5StickC Plus 2 |
| MCU | ESP32 |
| Display | ST7789 135×240 LCD (landscape: 240×135); layout adapts to other resolutions |
| IMU | MPU6886 6-axis accelerometer/gyroscope |
| PMIC | AXP2101 (battery management) |
| Communication | Bluetooth Low Energy (BLE 4.2) |

## Building

This is a [PlatformIO](https://platformio.org/) project targeting the Arduino framework. Use the `flash` script to build and upload in one step:

```bash
./flash                  # build + flash to m5stickc-plus2 (default)
./flash m5stickc-plus2
./flash m5stack-core2
./flash m5stack-grey
./flash m5stack-cores3
./flash -h               # show usage
```

Compilation is incremental — only changed files are recompiled. The script replaces the old separate `build` and `deploy` scripts.

### Supported board environments

| Environment | Board | Platform |
|---|---|---|
| `m5stickc-plus2` | M5StickC Plus 2 | espressif32 @ 6.1.0 |
| `m5stack-core2` | M5Stack Core2 | espressif32 @ 6.1.0 |
| `m5stack-grey` | M5Stack Grey | espressif32 @ 6.1.0 |
| `m5stack-cores3` | M5Stack CoreS3 | espressif32 @ 7.x |

The source uses **M5Unified** (`m5stack/M5Unified`) rather than the device-specific `M5StickCPlus2` library. `M5.Imu.isEnabled()` and `M5.Speaker.isEnabled()` guards are used throughout so the firmware degrades gracefully on boards that lack an IMU or speaker — the clinometer screen shows `IMU N/A` and BEEP commands are silently skipped. The display layout adapts to the actual screen dimensions reported by `M5.Display` after `setRotation()`: all pixel coordinates, margins, bar sizes, and bubble radii are derived from `width()` and `height()` at start-up, so the same code renders correctly on the M5StickC Plus 2 (240×135) and on larger displays such as the Core2 or CoreS3 (320×240).

### CoreS3 note

CoreS3 uses ESP32-S3, which requires `espressif32@7.x`. PlatformIO downloads it automatically on first build for that environment. You also need `intelhex` in PlatformIO's own virtualenv:

```bash
~/.platformio/penv/bin/pip install intelhex
```

## Screens

The **M5 front button** cycles through screens in order:

| # | Screen | Description |
|---|---|---|
| 0 | Clinometer | Bubble level with 1°/2°/3° rings, numeric Pitch/Roll readout |
| 1 | Time | Current time HH:MM:SS; timezone/LST label centered in cyan at the top (if set). Solar: date below the digits. Sidereal: no date. |
| 2 | RA/Dec | Right Ascension and Declination from the telescope |
| 3 | Alt/Az | Altitude and Azimuth from the telescope |
| 4 | Battery | Charge bar with colour coding, voltage (V) and level (%) |
| — | Message | Temporary full-screen overlay triggered by BLE command |

The display auto-rotates 180° based on the raw IMU gravity reading. When the screen's current top edge drifts more than ~17° past vertical away from physical up, the display flips to the opposite landscape orientation and flips back once the original orientation is again more than ~17° closer to physical up. All screens and overlays rotate together.

## Button behaviour

| Button | Short press | Long press (≥2 s) |
|---|---|---|
| M5 (front) | Cycle to next screen | — |
| Top (side) | Reboot | Play shutdown melody, then power off (AXP192 shutdown) |
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

**Input sanitisation:** Before tokenising each command write the device normalises two common non-ASCII space variants to ASCII space: NBSP (U+00A0, `C2 A0`) and ideographic space (U+3000, `E3 80 80`). Commands pasted from iOS/Android keyboards or copy-pasted text that contains these variants therefore parse correctly without client-side workarounds. If the write contains any other ASCII control character (byte value `< 0x20` or `0x7F`) after the trailing-whitespace strip, the write is rejected immediately with `ERR INVALID_CHAR U+XXXX` where `XXXX` is the hex code point of the first offending byte.

Subscribe to notifications on the **Response** characteristic to receive replies and asynchronous events (button presses, screen changes). The device sends one notify per command reply.

---

## BLE Commands

### `HELP`

Returns a concise list of all accepted commands. The device sends one notify packet per command line. `HELP` is always the last packet and serves as the stream terminator — no separate `OK` is sent.

```
→ HELP
← PING
← GET_TILT
← CALIBRATE [gx gy gz]
← CALIBRATE_RESET
← GET_STATUS
← GET_TIME
← GET_RADEC
← GET_ALTAZ
← GET_MSG
← SET_TIME <ISO8601+offset> [<label>]
← SET_TIME_ZONE <+HH:MM|-HH:MM|UTC|LST> [label]
← SET_LONGITUDE <degrees|NONE>
← SET_RADEC <ra> <dec>
← SET_ALTAZ <alt> <az>
← SHOW_MSG <dur> [FONT:<n>] [BEEP] <text...>
← SHOW_MSG_WAIT <dur> <btns> [FONT:<n>] [BEEP] <text...>
← CANCEL_MSG
← START_STREAM <ms>
← STOP_STREAM
← SET_NIGHT_MODE ON|OFF
← BEEP [<notes...>]
← PERSIST [CLEAR|RESTORE|READ]
← REBOOT
← HELP
```

Clients should subscribe to notifications and collect packets until they receive `HELP`. `?` is accepted as a synonym.

---

### `PING`

Returns a liveness acknowledgement.

```
→ PING
← OK PONG
```

---

### `GET_TILT`

Returns the current **pitch**, **roll**, and **gravity magnitude** in decimal degrees and g respectively.

```
→ GET_TILT
← TILT +0.42 -1.17 1.00
```

The first value is **pitch** (tilting the screen toward or away from you — rotation around the device's long axis), the second is **roll** (side tilt — rotation around the short axis), and the third is the **gravity vector magnitude in g**. Both angles are computed from all three raw accelerometer components using `atan2`, so they cover the full ±180° range without wrapping or clamping. The g value is ~1.00 when the device is stationary; it rises when the device is accelerating or vibrating, which signals that the current pitch/roll reading may be noisy.

**Angle convention** — the clinometer reports user-facing angles, not raw IMU Euler values. For every supported device the firmware first defines a screen-aligned UX frame:

```
UX +X = screen right
UX +Y = screen up
UX +Z = out of the screen, toward the viewer
```

Then it applies a fixed sign convention:

```
positive pitch = top of screen rises    (+ rotation about UX +X)
positive roll  = right side rises       (− rotation about UX +Y, intentional sign reversal)
```

The roll sign reversal is intentional. A mathematically positive right-hand-rule rotation about UX `+Y` would lower the screen-right side; the project inverts this so that positive roll always means the right side rises. For the recommended telescope mounting — screen-right side toward the aperture — positive roll therefore means the aperture side rises, i.e. altitude increases.

![IMU axes diagram](docs/adr/m5_imu_axes.jpg)

```
Device lying flat, screen facing up — UX frame as seen from above:

          screen up
             ↑  UX +Y
             |
             |
  UX +X ─────┼─────→  screen right
             |
             |
          (UX +Z points out of the screen, toward you)

positive pitch: the UX +Y edge rises  (top of screen lifts)
positive roll:  the UX +X edge rises  (right side of screen lifts)
```

See [`docs/adr/0002-angle-convention.md`](docs/adr/0002-angle-convention.md) for full derivations and per-device mappings.

**Axis mapping** is device-dependent and detected at runtime via `M5.getBoard()`:

| Device | Pitch formula | Roll formula | Pitch axis | Roll axis |
|---|---|---|---|---|
| M5StickC Plus / Plus2 | `atan2(-ax, az)` | `atan2(ay, az)` | X | Y |
| Core2, CoreS3, Grey, others | `atan2(ay, az)` | `atan2(-ax, az)` | Y | X |

The IMU inside the StickC series is mounted so that its X axis runs along the physical long axis of the case; tipping the long end therefore changes the X gravity component. Core2 / CoreS3 have the IMU oriented the other way around.

**Reconstructing the acceleration vector** from `TILT <pitch> <roll> <g>`:

The three values are sufficient to recover the full calibrated gravity vector. Let α = pitch in radians, β = roll in radians. Define:

```
D = sqrt(cos²β + sin²β · cos²α)
```

Then for **M5StickC Plus / Plus2** (pitch = `atan2(-ax, az)`, roll = `atan2(ay, az)`):

```
accX = −g · sin(α) · cos(β) / D
accY = +g · sin(β) · cos(α) / D
accZ = +g · cos(α) · cos(β) / D
```

For **Core2, CoreS3, others** (pitch = `atan2(ay, az)`, roll = `atan2(-ax, az)`):

```
accX = −g · sin(β) · cos(α) / D
accY = +g · sin(α) · cos(β) / D
accZ = +g · cos(α) · cos(β) / D
```

D equals 1 when either angle is zero and decreases toward the extremes; for angles below ~30° it is within 5% of 1, and the familiar small-angle approximation `accX ≈ −g·sin(pitch)`, `accY ≈ g·sin(roll)`, `accZ ≈ g` (StickC) or `accX ≈ −g·sin(roll)`, `accY ≈ g·sin(pitch)` (Core2) is accurate to the same order.

When a `CALIBRATE` offset is active, these are in the **calibrated frame of reference** — the origin of pitch = 0, roll = 0 is the stored reference orientation, not the hardware default. `CALIBRATE_RESET` returns to the hardware frame (device flat and face-up).

**Upside-down behaviour:** when the device is perfectly inverted and level (pitch/roll near ±180°) both values approach ±180°, correctly indicating that it is level but face-down. The on-screen bubble uses `sin(angle)` for its position so it smoothly re-centres at ±180° — the bubble sits at the centre of the circle whether the device is face-up or face-down level. The numeric display and this response always show the true angle.

Values update at ~15 Hz internally; the response reflects the most recent filtered sample.

---

### `CALIBRATE [gx gy gz]`

Without arguments, stores the current orientation as the pitch = 0, roll = 0 reference and returns the normalised reference gravity vector that encodes it:

```
→ CALIBRATE
← CALIBRATED +0.0023 -0.0150 +0.9999
```

With three arguments, restores a previously saved reference vector directly — no need for the device to be in the calibrated orientation:

```
→ CALIBRATE +0.0023 -0.0150 +0.9999
← CALIBRATED +0.0023 -0.0150 +0.9999
```

Both forms return the same `CALIBRATED gx gy gz` format. The calibration is held in RAM and is cleared on reboot. To survive a power cycle, either:

- Send `PERSIST` after calibrating — the device restores the calibration automatically on the next boot, or
- Record the three numbers from the response and send `CALIBRATE <gx> <gy> <gz>` after each reboot to restore manually.

Calibration is implemented as a 3×3 Rodrigues rotation matrix applied to the raw accelerometer vector before angle extraction. It works correctly for any starting orientation — not just small corrections.

---

### `CALIBRATE_RESET`

Removes the calibration and restores the hardware reference (device flat and face-up = 0°, 0°).

```
→ CALIBRATE_RESET
← OK CALIBRATION_RESET
```

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

Returns the current time, ticking locally since the last `SET_TIME`.

The response format depends on the active mode:

| Mode | Example response |
|---|---|
| Solar, no time set | `TIME NONE` |
| Solar | `TIME 2026-04-19T18:42:10Z` |
| Sidereal, longitude configured | `TIME 18:42:10 LST` |
| Sidereal, no longitude | `TIME 18:42:10 GST` |

```
→ GET_TIME
← TIME 2026-04-19T18:42:10Z       (solar — always UTC with Z suffix)
← TIME 18:42:10 LST               (sidereal with longitude — no date)
← TIME 18:42:10 GST               (sidereal without longitude — no date)
← TIME NONE                       (no time set yet)
```

Solar mode **always returns UTC with a `Z` suffix**. The device never returns local time from this command; the client applies its own UTC offset for display purposes. Use `SET_TIME_ZONE` to configure the local offset for the on-device TIME screen.

In sidereal mode the date is omitted. The label is `LST` (Local Sidereal Time) when an observer longitude has been configured via `SET_LONGITUDE`, or `GST` (Greenwich Sidereal Time) when no longitude has been set.

Returns `TIME NONE` if no time has been set since boot.

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

← MSG ACTIVE INF FONT=5 BUTTONS=M5 TEXT=Press M5 to continue
← MSG ACTIVE 4 FONT=0 BUTTONS=NONE TEXT=Moving altitude axis
```

The second field is the remaining lifetime in seconds, or `INF` for a persistent message. `FONT=<n>` is the active font code (see the font code table under `SHOW_MSG`); code 0 is the default `Font4`.

---

### `SET_TIME <iso8601> [<label>]`

Sets the device clock to the given UTC time and switches to solar mode. The device ticks locally from this point.

```
→ SET_TIME 2026-05-14T12:30:00Z
← OK TIME

→ SET_TIME 2026-05-14T12:30:00+01:00
← OK TIME

→ SET_TIME 2026-05-14T12:30:00 CET
← OK TIME

→ SET_TIME 2026-05-14T12:30:00-05:00 New York
← OK TIME

→ SET_TIME 2026-05-14T12:30:00 東京標準時間
← OK TIME

← ERR BAD_TIME
```

The datetime is always `YYYY-MM-DDTHH:MM:SS`. A `+HH:MM` / `-HH:MM` offset suffix is **parsed and subtracted**, so the device stores true UTC — for example, `2026-05-14T12:30:00+01:00` stores `11:30:00 UTC`. Everything after the datetime on the command line is used as the label, verbatim including any internal spaces, so multi-word timezone names such as `New York` are supported. The label is for display purposes only and does not affect the stored UTC time. The label may be any UTF-8 string up to 31 bytes, including multi-byte scripts such as Japanese (`東京標準時間`).

The UTC time is written to the hardware RTC (PCF8563). On the next power-on the device reads the RTC and rebuilds the running clock automatically. The timezone label and UTC offset are not stored in the RTC; use `PERSIST` to save them to NVM.

On devices without an onboard RTC (e.g. **M5Stack Grey**) the RTC write is silently skipped. The clock still ticks correctly for the rest of the session — `GET_TIME` returns the correct time and the TIME screen advances normally — but the time anchor is not preserved across power cycles. After each reboot `SET_TIME` must be re-sent.

| Suffix | UTC stored | Label default | Example |
|---|---|---|---|
| `Z` | Datetime as-is | `UTC` | `2026-05-14T12:30:00Z` |
| `+HH:MM` / `-HH:MM` | Offset subtracted | offset string | `2026-05-14T12:30:00+01:00` |
| separate label | Datetime as-is | label (spaces preserved) | `2026-05-14T12:30:00 New York` |
| (none) | Datetime as-is | nothing | `2026-05-14T12:30:00` |

No DST logic is applied. To change the display timezone after setting the time, use `SET_TIME_ZONE` — there is no need to re-send `SET_TIME`.

---

### `SET_TIME_ZONE <spec> [<label>]`

Sets the display timezone or switches to sidereal mode. Does not alter the stored UTC time.

```
→ SET_TIME_ZONE +09:00
← OK TIMEZONE

→ SET_TIME_ZONE +09:00 JST
← OK TIMEZONE

→ SET_TIME_ZONE +09:00 東京標準時間
← OK TIMEZONE

→ SET_TIME_ZONE +09:00 東京 (標準時)
← OK TIMEZONE

→ SET_TIME_ZONE UTC
← OK TIMEZONE

→ SET_TIME_ZONE LST
← OK TIMEZONE

→ SET_TIME_ZONE +bad
← ERR BAD_TZ

← ERR BAD_ARGS
```

| `<spec>` | Effect |
|---|---|
| `+HH:MM` / `-HH:MM` | Solar mode; sets UTC offset in seconds; label defaults to the offset string |
| `UTC` | Solar mode; UTC offset = 0; label `UTC` |
| `LST` | Sidereal mode; label is `LST` if a longitude is configured, else `GST` |

Everything after `<spec>` on the command line overrides the display label shown in the top-left of the TIME screen, verbatim including any internal spaces — so `SET_TIME_ZONE +09:00 JST` shows `JST` and `SET_TIME_ZONE +09:00 東京 (標準時)` shows `東京 (標準時)`. The label may be any UTF-8 string up to 31 bytes, including multi-byte scripts such as Japanese. The label is informational only; the UTC offset is what drives the clock arithmetic.

Timezone changes take effect immediately for the TIME screen and `GET_TIME`. Use `PERSIST` to save the setting across reboots.

---

### `SET_LONGITUDE <degrees|NONE>`

Sets the observer longitude used for Local Sidereal Time computation, or clears it.

```
→ SET_LONGITUDE 135.5
← OK LONGITUDE

→ SET_LONGITUDE -3.7
← OK LONGITUDE

→ SET_LONGITUDE NONE
← OK LONGITUDE

← ERR BAD_ARGS   (out of ±180° range or non-numeric)
```

Degrees east of Greenwich; negative for west. Valid range is −180.0 to +180.0. Once set, `GET_TIME` in sidereal mode returns `HH:MM:SS LST` instead of `GST`, and the TIME screen label switches accordingly. `NONE` clears the longitude (reverts to GST mode if sidereal is active).

Use `PERSIST` to save the longitude across reboots.

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

### `SHOW_MSG <duration> [FONT:<n>] [BEEP] <text>`

Displays a message on the full-screen message overlay.

```
→ SHOW_MSG 5 Moving altitude axis
→ SHOW_MSG INF Waiting for solar centering
→ SHOW_MSG 10 FONT:5 Slewing to α Centauri
→ SHOW_MSG 3 BEEP Alignment complete
→ SHOW_MSG INF FONT:6 BEEP ¡Atención!
← OK MSG
← ERR BAD_ARGS
```

| `<duration>` | Meaning |
|---|---|
| Integer (seconds) | Message auto-dismisses after this many seconds |
| `INF` | Message persists until `CANCEL_MSG` or a replacement |

The device switches to the message screen immediately and returns to the previous screen when the message expires or is cancelled. BLE and IMU continue running in the background.

`FONT:<n>` and `BEEP` are optional tokens parsed from the front of the text field; once a token does not match either keyword, all remaining text (including that token) becomes the message body. This means the message body itself must not begin with `FONT:` or the word `BEEP` unless those are intended to be consumed as options.

`BEEP` triggers an immediate short attention tone (880 Hz, 200 ms) when the message appears. For a custom melody, send a separate `BEEP` command before or after `SHOW_MSG`.

#### Font codes

| Code | Font | Approx. height | Character coverage |
|------|------|----------------|--------------------|
| 1 | `Font2` (Bodmer BMPfont) | 16 px | ASCII 0x20–0x7E only |
| 2 | `Font4` (Bodmer BMPfont) — **default** | 26 px | ASCII 0x20–0x7E only |
| 3 | `DejaVu18` (Adafruit GFX) | ~18 px | ASCII 0x20–0x7E only |
| 4 | `DejaVu24` (Adafruit GFX) | ~24 px | ASCII 0x20–0x7E only |
| 5 | `lgfxJapanGothic_16` (U8g2) | 16 px | Full Unicode incl. Latin-1 extended (é, ü, ñ …) |
| 6 | `lgfxJapanGothic_24` (U8g2) | 24 px | Full Unicode incl. Latin-1 extended (é, ü, ñ …) |

Fonts 1–4 are bitmap or proportional sans-serif fonts that cover standard ASCII printable characters only. Accented letters, currency symbols (€, £), and other characters above U+007E will not render with those fonts — use code 5 or 6 instead. `lgfxJapanGothic` is a U8g2 Unicode font that also handles CJK characters.

The default (no `FONT:` token, or `FONT:0` / `FONT:2`) is `Font4`, which is noticeably larger than the original `Font2` used before this feature was added.

**Automatic Unicode upgrade:** if the message text contains any non-ASCII byte (≥ 0x80) and no `FONT:` token was supplied, the device automatically selects `lgfxJapanGothic_24` (code 6, 24 px) to closely match the default Font4 (26 px) visual size while supporting the full Unicode character set. An explicit `FONT:` directive is always honoured as-is and disables the upgrade. The active font code is visible in the `GET_MSG` response as `FONT=<n>`.

**Text wrapping:** the message text is automatically wrapped to fit the display width. The device breaks at word boundaries (spaces) where possible. When a single word is too wide to fit on one line — as is common in languages that do not use spaces, such as Japanese — the device falls back to character-level splitting. All UTF-8 multi-byte sequences are kept intact; no code point is split across lines. This means long Japanese strings such as `今日も小さな幸せがたくさん見つかりますように` and long ASCII tokens without spaces (such as URLs) wrap across multiple lines rather than being clipped.

---

### `SHOW_MSG_WAIT <duration> <buttons> [FONT:<n>] [BEEP] <text>`

Displays a message and registers interest in one or more button presses. When a watched button is pressed, the device sends an `EVENT BUTTON <x>` notification.

```
→ SHOW_MSG_WAIT 30 M5 Press M5 when ready
→ SHOW_MSG_WAIT INF M5,A Confirm or abort
→ SHOW_MSG_WAIT 15 ANY Press any button to stop
→ SHOW_MSG_WAIT INF M5 FONT:5 BEEP ¿Continuar?
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

`FONT:<n>` and `BEEP` work identically to `SHOW_MSG` — see the font code table above. The message remains visible after a button press until its timeout expires or `CANCEL_MSG` is received. Multiple button events can be generated if the user presses the button more than once.

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

Minimum period is 100 ms. Streaming continues until `STOP_STREAM` or disconnection. Because streaming is tied to a connection, `START_STREAM` and the notification subscriber must be on the **same BLE connection** — use `m5ctl listen --stream <ms>` rather than separate `stream` and `listen` calls.

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

### `BEEP [note ...]`

Plays a beep or a melody through the built-in speaker. The response is returned immediately while the melody plays asynchronously.

```
→ BEEP
← OK BEEP

→ BEEP C'4 G8 -16 G8 A4 G4 -2 B4 C'4
← OK BEEP

→ BEEP C4 Z4
← ERR BAD_MELODY C4 ^Z4
```

With no arguments the device emits a single short attention beep (880 Hz, 200 ms). With note tokens it plays the sequence as a melody.

**Note token format:** `<letter>[accidental][octave][duration][dot]`

Each token is a space-separated note or rest:

| Part | Syntax | Meaning |
|---|---|---|
| Letter | `A` `B` `C` `D` `E` `F` `G` | Note name (case-insensitive) |
| Rest | `-` | Silence for the given duration |
| Sharp / flat | `#` or `b` after letter | Raise or lower by one semitone |
| Octave up | `'` (one or more) after accidental | Each `'` raises the note by one octave |
| Octave down | `,` (one or more) after accidental | Each `,` lowers the note by one octave |
| Duration | `1` `2` `4` `8` `16` | Whole, half, quarter, eighth, sixteenth; default `4` |
| Dotted | `.` after duration | Multiplies duration by 1.5 |

Bare letter names (no `'` or `,`) are in the middle register. A single `'` shifts up one octave from there; a single `,` shifts down one octave. Multiple marks stack: `C''` is two octaves above the middle C, `C,,` is two below.

**Examples:**

| Token | Meaning |
|---|---|
| `C` | Middle C, quarter note |
| `C'` | One octave above middle C, quarter note |
| `C,` | One octave below middle C, quarter note |
| `G#8` | G sharp, eighth note |
| `Bb2` | B flat, half note |
| `C4.` | Dotted quarter (1.5× duration) |
| `-4` | Quarter-note rest |

"Shave And A Hair Cut":

```
BEEP C'4 G8 -16 G8 A4 G4 -2 B4 C'4
```

Up to 32 notes per command.

---

### `PERSIST [CLEAR|RESTORE|READ]`

Manages non-volatile storage of user settings. Four values can be persisted: the **timezone label**, **UTC offset**, **observer longitude**, and **calibration reference vector**. NVM writes happen only on an explicit `PERSIST` command — no write occurs during `SET_TIME`, `SET_TIME_ZONE`, `SET_LONGITUDE`, `CALIBRATE`, or `CALIBRATE_RESET`.

#### `PERSIST`

Saves the current timezone label, UTC offset, observer longitude, and calibration reference vector to NVM. Data keys are written first; the validity flag is written last so a power loss mid-write leaves NVM in a clean invalid state.

```
→ PERSIST
← OK PERSISTED tz=JST tz_offset=32400 lon=135.5000 cal=+0.0023,-0.0150,+0.9999
← OK PERSISTED tz=UTC tz_offset=0 lon=(none) cal=+0.0023,-0.0150,+0.9999
```

On the next power-on the device restores all saved values automatically. The UTC time itself is always recovered from the hardware RTC; sidereal phase is recomputed from UTC + longitude using the GMST formula, so the sidereal clock continues correctly without any stored sidereal state.

#### `PERSIST CLEAR`

Invalidates all stored NVM settings with a **single flash write** (sets an internal validity byte to 0). Data keys are left in flash but ignored on boot. This is the lowest-wear way to clear settings.

```
→ PERSIST CLEAR
← OK CLEARED
```

#### `PERSIST RESTORE`

Re-enables the stored NVM settings (sets the validity byte back to 1) and immediately applies them to the current device state — **no reboot required**. The response shows the values that were applied.

```
→ PERSIST RESTORE
← OK RESTORED tz=UTC tz_offset=0 lon=(none) cal=+0.0023,-0.0150,+0.9999
```

Useful after `PERSIST CLEAR` to roll back without rebooting: the data keys are still in flash and can be re-activated in-session with one write.

#### `PERSIST READ`

Returns the current NVM contents without modifying anything. Shows the validity flag and all stored keys. If `valid=0` the data is present in flash but will not be applied on the next boot.

```
→ PERSIST READ
← PERSIST valid=1 tz=UTC tz_offset=0 lon=(none) cal=+0.0023,-0.0150,+0.9999
```

| Field | Meaning |
|---|---|
| `valid` | `1` = data will be restored on next boot; `0` = data ignored |
| `tz` | Stored timezone label, or `(none)` |
| `tz_offset` | UTC offset in seconds (e.g. `32400` = JST +09:00; `0` = UTC) |
| `lon` | Observer longitude °East, or `(none)` when not configured |
| `cal` | Stored calibration reference vector `gx,gy,gz`, or `(none)` for identity |

---

### `REBOOT`

Performs a software reset. The device sends `OK REBOOTING`, waits ~200 ms for the notification to be delivered, then calls `ESP.restart()`. The BLE connection drops and the device re-advertises after boot. Any settings saved with `PERSIST` are restored automatically.

```
→ REBOOT
← OK REBOOTING
```

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

When `START_STREAM` is active, periodic tilt notifications are sent in the same format as `GET_TILT` — pitch, roll, gravity magnitude in g:

```
TILT +0.38 -1.12 0.99
```

---

## Error responses

| Response | Meaning |
|---|---|
| `ERR UNKNOWN_COMMAND` | Command token not recognised |
| `ERR BAD_ARGS` | Wrong number or format of arguments |
| `ERR BAD_TIME` | `SET_TIME` value could not be parsed |
| `ERR BAD_TZ` | `SET_TIME_ZONE` offset spec is malformed (e.g. `+bad` or `+5` without minutes) |
| `ERR BAD_MELODY <melody>` | `BEEP` received an unrecognised note token; the melody string is echoed back with `^` inserted before the first invalid token |
| `ERR INVALID_CHAR U+XXXX` | Command write contained an ASCII control character; `XXXX` is the hex code point of the first offending byte. NBSP (U+00A0) and ideographic space (U+3000) are normalised to space and do not trigger this error. |

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
uv sync                  # create .venv with all dependencies
uv sync --group dev      # include pytest / pytest-asyncio for running tests
uv sync --group tools    # include pygame and PyOpenGL for the 3D viewer
```

### tools/m5ctl

`tools/m5ctl` is a Python 3 command-line client for the BLE interface.

```
usage: m5ctl [-h] [-d ADDR_OR_NAME] [-t SEC] COMMAND ...

options:
  -d ADDR_OR_NAME   Device address or config name. Priority: --device > $M5_BLE_ADDR > default_device > first conf entry
  -t SEC            seconds to wait for a response (default: 5)
```

| Command | Arguments | Description |
|---|---|---|
| `version` | | Show m5ctl version (no device required) |
| `list` | | Scan configured devices for reachability and print a table (1-second scan; no device required) |
| `scan` | `[--timeout SEC]` | Scan for nearby BLE devices; annotates devices found in the conf file with their config name (default 3-second scan) |
| `help` | | List all accepted BLE commands |
| `ping` | | Ping the device |
| `tilt` | | Get current pitch/roll angles |
| `calibrate` | `[gx gy gz]` | Calibrate from current orientation (no args) or restore a saved reference vector |
| `calibrate-reset` | | Remove calibration and restore hardware reference |
| `status` | | Get device status (screen, BLE, battery, stream, night mode) |
| `get-time` | | Get current device time |
| `get-radec` | | Get stored RA/Dec values |
| `get-altaz` | | Get stored Alt/Az values |
| `get-msg` | | Get current message state |
| `set-time` | `<iso8601> [<label>]` | Set device clock (offset subtracted to store UTC); optional label for display |
| `set-time-now` | `[--utc\|--local\|--timezone TZ] [--offset N]` | Set device clock to the current host time; local time auto-appends the system TZ abbreviation as label |
| `set-timezone` | `<spec> [label]` | Set display timezone or switch to sidereal mode; spec may be `+HH:MM`/`-HH:MM`, `UTC`, `LST`, a TZ abbreviation (`CET`, `JST`, …), or an IANA name (`Europe/Madrid`); use `~` instead of `-` for negative offsets |
| `set-longitude` | `<degrees>` | Set observer longitude °East for LST computation |
| `set-radec` | `<ra> <dec>` | Set RA/Dec display values |
| `set-altaz` | `<alt> <az>` | Set Alt/Az display values |
| `show-msg` | `<seconds\|inf> [FONT:<n>] [BEEP] <text>` | Display a timed or persistent message; optional font code and/or beep |
| `show-msg-wait` | `<seconds\|inf> <buttons> [FONT:<n>] [BEEP] <text>` | Display a message and watch for a button press |
| `cancel-msg` | | Cancel the active message immediately |
| `listen` | `[--stream <ms>]` | Print all BLE notifications; `--stream <ms>` also starts tilt streaming on the same connection |
| `stop-stream` | | Disable tilt streaming |
| `night-mode` | `on\|off` | Enable or disable red-only night mode |
| `beep` | `[note ...]` | Play a beep or melody (omit notes for a standard beep) |
| `persist` | | Save timezone label, UTC offset, longitude, and calibration to NVM |
| `persist-read` | | Show stored NVM values (validity flag and all keys) |
| `persist-clear` | | Invalidate stored NVM settings with a single flash write |
| `persist-restore` | | Re-enable and apply last stored NVM values in-session (no reboot) |
| `reboot` | | Software-reset the device |

Examples:

```bash
uv run tools/m5ctl version
uv run tools/m5ctl list
uv run tools/m5ctl scan
uv run tools/m5ctl -d main tilt           # select by config name (device.main = MAC in conf)
uv run tools/m5ctl -d 0 tilt             # select by numeric key  (device.0  = MAC in conf)
uv run tools/m5ctl help
uv run tools/m5ctl tilt
uv run tools/m5ctl status
uv run tools/m5ctl set-time-now
uv run tools/m5ctl set-time-now --utc
uv run tools/m5ctl set-time-now --timezone Europe/Madrid
uv run tools/m5ctl set-time-now --timezone CEST
uv run tools/m5ctl set-time "2026-05-14T12:30:00Z"
uv run tools/m5ctl set-time "2026-05-14T12:30:00+01:00"
uv run tools/m5ctl set-time "2026-05-14T12:30:00" CET
uv run tools/m5ctl set-timezone JST               # resolves to +09:00, label JST
uv run tools/m5ctl set-timezone CET               # resolves to +01:00, label CET
uv run tools/m5ctl set-timezone Europe/Madrid     # resolves current offset, label Europe/Madrid
uv run tools/m5ctl set-timezone +09:00 JST        # explicit offset with label
uv run tools/m5ctl set-timezone ~05:00 EST        # negative offset (~ avoids argparse flag conflict)
uv run tools/m5ctl set-timezone LST
uv run tools/m5ctl set-longitude 135.5
uv run tools/m5ctl set-radec "12:34:56" "+07:08:09"
uv run tools/m5ctl night-mode on
uv run tools/m5ctl beep
uv run tools/m5ctl beep "C'4 G8 -16 G8 A4 G8 -2 B4 C'4"
uv run tools/m5ctl persist                # save tz, offset, longitude, calibration to NVM
uv run tools/m5ctl persist-read           # inspect NVM contents
uv run tools/m5ctl persist-clear          # invalidate NVM (1 flash write)
uv run tools/m5ctl persist-restore        # re-enable and apply stored NVM values
uv run tools/m5ctl reboot                 # software-reset the device
uv run tools/m5ctl listen --stream 500
uv run tools/m5ctl listen
```

### Device address configuration

The device is resolved from `-d ADDR_OR_NAME` in this order:

1. **Raw MAC** — `--device AA:BB:CC:DD:EE:FF` passes through directly.
2. **Config name** — `--device main` looks up `device.main` in the conf file; exits with an error if not found.
3. **No `-d`, env var set** — uses `M5_BLE_ADDR`.
4. **No `-d`, no env var** — uses `default_device` from the conf file if present; otherwise uses the first `device.NAME` entry in the conf file.

Config file lookup searches the following locations, stopping at the first match:

   **Running from Python source (`uv run tools/m5ctl …` or `uv run python tests/3d_model.py …`):**
   | Location | Filename | Notes |
   |---|---|---|
   | Project root | `.m5ctl.conf` | Standard location (gitignored hidden file) |
   | Project root | `m5ctl.conf` | Windows-friendly alternative — no leading dot; also gitignored |
   | Home directory | `~/.m5ctl.conf` | Per-user fallback |

   Both `tools/m5ctl` and `tests/3d_model.py` use this same search order, so a single conf file at the project root is shared by both tools.

   **Running as a PyInstaller frozen executable (`m5ctl.exe …`):**
   | Location | Filename | Notes |
   |---|---|---|
   | Next to the executable | `m5ctl.conf` | Preferred for portable Windows installs |
   | Home directory | `~/.m5ctl.conf` | Per-user fallback |

**Single device** — create `.m5ctl.conf` at the project root:

```ini
# .m5ctl.conf — gitignored, do not commit
device.main = F0:24:F9:9B:E2:52
```

With a single entry, `m5ctl tilt` (no `-d`) automatically picks it up — no extra config needed.

**Multiple devices** — use `device.NAME` entries (dot notation):

```ini
# .m5ctl.conf — gitignored, do not commit
device.main  = F0:24:F9:9B:E2:52 M5StickC Plus2 on telescope mount
device.guide = 3C:AB:CD:EF:01:56 M5StickC Plus2 on guide scope
device.grey  = 80:EF:AB:CD:12:36 M5Stack Grey (spare)   # powered off
```

The key after the dot is the name shown in `m5ctl list`. Numeric names (`device.0`, `device.1`) are accepted.

An optional **annotation** can follow the MAC address (separated by whitespace). Everything between the end of the MAC and the first `#` (or end of line) becomes the annotation, trimmed of surrounding whitespace. Annotations are free-form text and may contain spaces. They appear as the last column in `m5ctl list` output and have no effect on device resolution. A `#` starts a comment that runs to the end of the line; it is stripped before the annotation is recorded.

**Setting a default device** — when no `-d` flag is given, `m5ctl` automatically uses the first `device.NAME` entry in the conf file. To override the file order and designate a specific entry as the default, add a `default_device` key:

```ini
device.main  = F0:24:F9:9B:E2:52 M5StickC Plus2 on telescope mount
device.guide = 3C:AB:CD:EF:01:56 M5StickC Plus2 on guide scope
device.grey  = 80:EF:AB:CD:12:36 M5Stack Grey (spare)
default_device = guide   # m5ctl tilt (no -d) uses device.guide
```

`default_device` must match an existing `device.NAME` key. A warning is printed to stderr if it names an unknown device, and the first entry is used as a fallback. `m5ctl list` marks the active default with a leading `*`.

`m5ctl list` performs a 1-second BLE scan and shows the reachability, RSSI, BLE-advertised name, and annotation (if configured) for every named entry. The active default device is marked with a leading `*`:

```
m5ctl 1.0
Config: /home/user/project/.m5ctl.conf
M5_BLE_ADDR: (not set)

* main   F0:24:F9:9B:E2:52  reachable     -36 dBm  M5-NexStar-Level      | M5StickC Plus2 on telescope mount
  guide  3C:AB:CD:EF:01:56  reachable     -49 dBm  M5-NexStar-Level      | M5StickC Plus2 on guide scope
  grey   80:EF:AB:CD:12:36  unreachable      —     (unknown)             | M5Stack Grey (spare)
```

The annotation column is omitted entirely for entries that have no annotation. It is prefixed with `|` to visually separate it from the BLE device name. When output is a terminal, `reachable` is shown in green, `unreachable` in red/dim, and the annotation (including its `|` prefix) in dim gray; plain text when piped.

`m5ctl scan` annotates any discovered device whose MAC appears in the conf file; known devices are shown in yellow/bold when output is a terminal. The scan duration defaults to 3 seconds and can be changed with `--timeout`:

```bash
m5ctl scan                 # 3-second scan (default)
m5ctl scan --timeout 1     # quick 1-second scan
m5ctl scan --timeout 8     # thorough 8-second scan
```

```
  F0:24:F9:9B:E2:52   -36 dBm  M5-NexStar-Level  [main]
  3C:AB:CD:EF:01:56   -49 dBm  M5-NexStar-Level  [guide]
  AA:BB:CC:DD:EE:FF   -72 dBm  iPhone
```

Once the file exists, all `m5ctl` calls pick it up automatically. If none of the sources provides an address, `m5ctl` exits with an error — `scan`, `list`, and `version` are the only subcommands that work without one.

### `set-time-now` — set device clock to current host time

```bash
uv run tools/m5ctl set-time-now                    # local time (label = system TZ abbreviation)
uv run tools/m5ctl set-time-now --utc              # UTC time (no label)
uv run tools/m5ctl set-time-now --timezone CEST    # time in CEST (UTC+2); label: CEST
uv run tools/m5ctl set-time-now --timezone Europe/Madrid  # IANA timezone; label: Europe/Madrid
uv run tools/m5ctl set-time-now --offset 0         # no latency compensation
```

`--utc`, `--local`, and `--timezone` are mutually exclusive. `--offset N` (default `3`) adds seconds to compensate for BLE connection latency, matching the behaviour of the old `set-utc-now` script.

Timezone resolution: IANA names (e.g. `Europe/Madrid`, `America/New_York`) are resolved via `zoneinfo`. Common abbreviations (`CET`, `CEST`, `EST`, `EDT`, `PST`, `PDT`, `JST`, `IST`, `AEST`, …) are mapped to their canonical IANA zone for time computation; the label shown on the device screen is always the string you passed.

`set-time-now` sends the current local time with the UTC offset embedded in the ISO 8601 string followed by the system timezone abbreviation as the display label (e.g. `SET_TIME 2026-05-21T20:05:16+02:00 CEST`). The device subtracts the offset to store true UTC, then uses the offset and label to display local time on screen. When `--utc` is used no label is sent; when `--timezone` is used the label is the string you passed.

### `set-timezone` — change display timezone without re-syncing the clock

```bash
uv run tools/m5ctl set-timezone CET                   # +01:00, label CET
uv run tools/m5ctl set-timezone CEST                  # +02:00, label CEST
uv run tools/m5ctl set-timezone JST                   # +09:00, label JST
uv run tools/m5ctl set-timezone Europe/Madrid         # current offset for that zone, label Europe/Madrid
uv run tools/m5ctl set-timezone CEST "Madrid/Europe"  # +02:00, explicit label
uv run tools/m5ctl set-timezone ~05:00 EST            # negative offset without argparse conflict
uv run tools/m5ctl set-timezone +09:00 JST            # explicit offset — passed straight through
uv run tools/m5ctl set-timezone UTC                   # UTC
uv run tools/m5ctl set-timezone LST                   # sidereal mode
```

`set-timezone` accepts the same TZ abbreviations and IANA zone names as `set-time-now --timezone`, but it only changes the display offset and label — it does **not** alter the stored UTC time. This is the right command when the clock is already set correctly and you just want to switch the on-screen timezone (for example, after flying to a different zone).

**Abbreviation resolution:** Known abbreviations (`CET`, `CEST`, `EST`, `EDT`, `PST`, `PDT`, `JST`, `IST`, `AEST`, …) are mapped to their **conventional fixed offsets** — `CET` is always `+01:00`, `CEST` is always `+02:00`, regardless of the current date. This is intentional: the abbreviation itself encodes the expected offset. IANA zone names (e.g. `Europe/Madrid`, `America/New_York`) resolve to the **current** UTC offset of that zone, including DST.

**Negative offsets:** argparse treats arguments starting with `-` as flags. The strictly correct POSIX way to pass a negative offset on a Linux terminal is `-- -07:00 PST` (the `--` signals end of options). The `~` alias (`~07:00 PST`) achieves the same result and is more portable across terminals (Windows CMD, PowerShell, macOS) where `--` may not be recognised or may behave differently; m5ctl translates `~` to `-` before sending the BLE command.

### tests/3d_model.py — real-time 3D orientation viewer

`tests/3d_model.py` connects to the device over BLE and renders a live 3D model that tracks the device's pitch and roll in real time. It requires the `tools` dependency group (pygame + PyOpenGL):

```bash
uv sync --group tools
```

It reads the same conf file as `m5ctl`, resolves device names and the `default_device` key with identical logic, and accepts `-d` (short form of `--device`) with an `ADDR_OR_NAME` argument — pass a raw MAC or a config name listed by `m5ctl list`. When no device is configured or found, it falls back to an interactive BLE scan instead of exiting with an error.

**Operating modes:**

| Mode | How triggered | Description |
|---|---|---|
| Config | No `-d`; conf file has `default_device` or any `device.NAME` entry | Connects automatically to the configured default (or first entry) |
| Named | `-d main` | Resolves `main` to its MAC via `device.main` in the conf file |
| Direct | `-d F0:24:F9:9B:E2:52` | Connects directly to the given raw MAC address |
| Scan | No `-d`; no conf entry found | Scans for BLE devices, shows a numbered list, prompts for selection |
| Simulator | `--sim` | Animated demo — no BLE required |

**Keyboard controls:**

| Key | Action |
|---|---|
| `1` | Switch to M5StickC Plus 2 model |
| `2` | Switch to M5Stack Core 2 model |
| `3` | Switch to M5Stack CoreS3 model |
| `Q` / `Esc` | Quit |

The viewer renders labeled X/Y/Z accelerometer axis arrows that match the physical orientation printed on each device. The HUD shows live pitch/roll angles, the reconstructed gravity vector, and BLE connection state. If the device disconnects, the last known orientation is held and the viewer auto-reconnects after ~3 seconds.

---

## Test suite

`tests/` contains a pytest suite that exercises the full BLE command interface against a real device, including the dynamic newline-framing protocol.

```bash
# Run all tests (device must be on and reachable)
uv run pytest

# Specify a non-default BLE address
uv run pytest --device AA:BB:CC:DD:EE:FF

# Run only a specific test module
uv run pytest tests/test_newline.py
uv run pytest tests/test_sanitize.py
```

### Persistence tests (`test_persistence.py`)

`tests/test_persistence.py` exercises the `PERSIST` command family and `REBOOT`. It is **excluded from the default `pytest` run** and must be invoked explicitly:

```bash
uv run pytest tests/test_persistence.py
uv run pytest tests/test_persistence.py --device AA:BB:CC:DD:EE:FF
```

The reason it is excluded is flash wear: every `PERSIST` or `PERSIST CLEAR` command writes to the ESP32 NVS flash. Running these tests on every CI or development `pytest` invocation would accumulate unnecessary write cycles. The exclusion is implemented via `addopts = "--ignore=tests/test_persistence.py"` in `pyproject.toml`; pytest's own rules ensure that an explicitly-supplied path on the command line overrides `--ignore`, so `pytest tests/test_persistence.py` still collects and runs all 14 tests.

Each test in the file is preceded by an autouse fixture that sends `PERSIST CLEAR` followed by `SET_LONGITUDE NONE` over BLE, giving every test a known starting state (`valid=0` in NVM and no longitude in RAM) regardless of what prior tests left behind. The two reboot tests (`test_persist_survives_reboot` and `test_clear_survives_reboot`) send the `REBOOT` command, wait 5 seconds for the device to restart and re-advertise, then reconnect and verify the NVM state that the boot loader applied.

Set the environment variable `M5_ADDR` as an alternative to `--device`.

---

## Project structure

```
├── flash                  Build + flash script; accepts env name, defaults to m5stickc-plus2
├── platformio.ini         Build config: M5Unified, espressif32, three board environments
├── pyproject.toml         Python dependencies and pytest config (managed by uv)
├── src/
│   ├── main.cpp           Arduino setup/loop — orchestrates all subsystems
│   ├── model/
│   │   └── DeviceState.h  Shared state struct accessed by all modules
│   ├── imu/
│   │   ├── ImuManager.h
│   │   └── ImuManager.cpp Pitch/Roll sampling at ~15 Hz; atan2 full-range formula, Rodrigues calibration matrix
│   ├── ble/
│   │   ├── BleManager.h
│   │   └── BleManager.cpp GATT server, command parser, response/event notify
│   ├── ui/
│   │   ├── Display.h
│   │   └── Display.cpp    All six screen renderers (sprite-buffered via M5GFX)
│   └── system/
│       ├── PowerManager.h/.cpp  M5Unified init, battery voltage/level, power-off
│       ├── Buttons.h/.cpp       Button polling, screen cycle, reboot/sleep
│       └── Nvm.h/.cpp           NVM persistence (Preferences, namespace "clino")
├── tools/
│   └── m5ctl              Python 3 BLE command-line client
├── tests/
│   ├── conftest.py        BleSession helper and pytest fixtures
│   ├── test_commands.py   BLE command interface tests
│   ├── test_newline.py    Newline-framing protocol tests
│   ├── test_sanitize.py   Input sanitisation tests (NBSP/ideographic-space normalisation, control-char rejection)
│   ├── test_m5ctl.py      Unit tests for m5ctl helpers (no device required — always run)
│   └── 3d_model.py        Real-time 3D orientation viewer (pygame + PyOpenGL)
└── docs/
    └── m5stickc-clinometer-ble-spec.md   Full design specification
```

## Architecture notes

- The BLE stack runs on its own FreeRTOS task (managed by the ESP32 Arduino BLE library). All other work runs in the Arduino `loop()` task.
- BLE callbacks write commands into a volatile hand-off buffer (`pendingBleResponse`); the main loop drains this buffer each tick and issues the BLE notify. This keeps all M5 hardware access (IMU, display, power) exclusively on the main loop task.
- Hardware is initialised through M5Unified (`M5Unified.h`); subsystems guarded with `M5.Imu.isEnabled()` / `M5.Speaker.isEnabled()` so the firmware degrades gracefully on boards without those peripherals. The display uses M5GFX sprite double-buffering for flicker-free rendering; sprites are allocated at **8-bit (palette) colour depth** so the full-screen buffer fits in internal SRAM on all supported display sizes — a 320×240 sprite at 16-bit would require ~150 KB, which cannot be allocated alongside the BLE stack on the ESP32; at 8-bit it drops to ~75 KB. All standard colours (black, white, red, green, yellow, grey variants) map exactly or near-exactly to the 216-entry web-safe palette used in this mode. All layout coordinates are computed from `M5.Display.width()` / `M5.Display.height()` cached once in `Display::begin()`, so every screen (bubble level, time, RA/Dec, Alt/Az, battery, message) scales proportionally to whatever resolution the target board reports.
- Non-volatile storage uses the ESP32 **NVS** (Non-Volatile Storage) via the Arduino `Preferences` library, namespace `"clino"`. The `huge_app.csv` partition table reserves 20 KB for NVS — the settings payload is under 50 bytes. NVS writes happen only on explicit `PERSIST` commands; a validity byte written last acts as an atomic commit flag so a power loss during a write leaves NVM cleanly invalid rather than partially written. `PERSIST CLEAR` costs exactly one NVS write (the validity byte); all data keys are left in flash and can be re-enabled by `PERSIST RESTORE`.
- The clock subsystem uses `esp_timer_get_time()` (int64_t µs, no 49-day wrap) to track elapsed time since the last UTC sync and to advance the Q40 fixed-point sidereal phase. All other timing uses non-blocking `millis()` gates — no `delay()` except the mandatory 1 ms yield at the end of each loop tick, the 200 ms drain wait before `ESP.restart()` on `REBOOT`, and the shutdown melody sequence in `PowerManager::deepSleep()` (blocking is acceptable in both cases since the device is about to reset or power off).
- Flash usage: ~55% of 3 MB. RAM usage: ~13% of 320 KB.

---

## Acknowledgements

Thanks to [@senshu-hiro](https://github.com/senshu-hiro) for the idea and initial implementation of the 3D orientation viewer, and for suggesting several features that made it into the firmware: the `BEEP` command, time-zone support in `SET_TIME`, the `CALIBRATE` command, multi-product support (Core 2 and CoreS3), and adaptive newline termination in BLE responses.

Thanks to [@senshu-hiro2](https://github.com/senshu-hiro2) for reporting the RTC-less device bug (M5Stack Grey) and submitting the patch that became Changes 1–5 in patch-23b: the `SET_TIME` in-memory anchor fix, `SET_TIME_ZONE` offset validation, `rebuildAnchor` conditional guard, timezone label centering, and the `~` alias for negative UTC offsets in `m5ctl`. Also for proposing the multi-device config format, `m5ctl list`, `m5ctl version`, and BLE connection retry — features that became Issues 1–5 of the m5ctl improvement series.

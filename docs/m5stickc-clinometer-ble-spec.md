# M5StickC Clinometer + BLE Telescope Helper

## Purpose

This project turns an M5StickC into a small handheld telescope helper for NexStar setup and solar alignment workflows.

The device shall:

* provide a **clinometer / bubble level** based on the IMU,
* expose a **BLE interface** so a nearby Raspberry Pi can query tilt and update displayed information,
* display several screens selectable with the front **M5 button**,
* remain useful as a standalone on-device tool even when BLE is not connected.

This is intentionally a **BLE-first** design. Wi-Fi features are out of scope for now.

---

## Project structure

Suggested repository layout:

```text
project/
├── demo/
│   ├── original/              # original vendor demos as received
│   ├── clinometer-tweaked/    # current working tweaked bubble-level version
│   └── notes.md               # optional notes about origin of demos / changes
├── docs/
│   └── m5stickc-clinometer-ble-spec.md
├── src/
│   ├── main.ino               # or main.cpp depending on chosen build style
│   ├── ui/
│   ├── ble/
│   ├── imu/
│   ├── system/
│   └── model/
└── README.md
```

Minimum expectation for now:

* keep the current implementation and demos under `demo/`,
* place this document in the repo as the working specification,
* build the new solution separately from the demo code.

---

## Functional scope

### Included

1. **Clinometer screen**

   * based on current tweaked implementation,
   * displays a bubble level,
   * shows concentric circles for approximately 1°, 2°, and 3°,
   * shows numeric X and Y tilt angles.

2. **Time screen**

   * displays current time,
   * time is set externally from the Raspberry Pi over BLE,
   * device may keep ticking locally between updates.

3. **RA/Dec screen**

   * displays the current Right Ascension and Declination values,
   * values are set externally from the Raspberry Pi over BLE.

4. **Alt/Az screen**

   * displays the current Altitude and Azimuth values,
   * values are set externally from the Raspberry Pi over BLE.

5. **Background BLE service**

   * always available while the device is running,
   * can answer queries and receive updates regardless of the foreground screen,
   * does not require the clinometer screen to be visible.

### Excluded for now

* Wi-Fi scanner
* Wi-Fi configuration
* HTTP API
* Sony Alpha camera control
* persistent network credentials

---

## User interface

## Screen navigation

The large front **M5 button** cycles through screens in this order:

1. Clinometer
2. Time
3. RA/Dec
4. Alt/Az
5. back to Clinometer

This button is only for screen selection.

## Top button

The **top button** keeps the same role as in the demo behavior:

* **short press** → reboot
* **long press** → shutdown / deep sleep / power-off behavior, as supported by the current demo base

## Third button

No essential use is currently required.

Recommended default:

* leave unused for now, or
* reserve it for a future utility action such as:

  * screen brightness toggle,
  * hold / freeze current screen values,
  * zero / calibrate tilt offset,
  * BLE advertising reset.

### Recommendation

The most potentially useful role for the third button is:

* **short press** → toggle screen brightness between a few preset levels,
* **long press** → zero / calibrate clinometer offset.

Reason:

* brightness control is handy in daylight/night use,
* tilt zeroing may be useful if the device is mounted in a non-perfect mechanical reference.

This remains optional and can be omitted in the first implementation.

---

## Runtime model

The device behaves as a small instrument with one active foreground screen and several background subsystems.

### Foreground

* current screen rendering
* button handling
* temporary message-screen override when a BLE message is active

### Background

* BLE advertising / connection / request handling
* periodic IMU sampling
* current tilt calculation
* timekeeping from last externally set time
* storage of the latest RA/Dec and Alt/Az values in memory
* message timeout tracking
* button-event generation for BLE

This means:

* BLE must continue working while any screen is shown,
* the device must be able to return tilt values even if the user is currently looking at the time, RA/Dec, or Alt/Az screen,
* the clinometer computation should not depend on the clinometer screen being active,
* an active message must not block BLE or background state updates,
* button presses may both affect local UI behavior and generate BLE events when applicable.

---

## Data model

A simple in-memory shared state is sufficient.

Suggested model:

```text
DeviceState
- screenIndex
- bleConnected
- batteryVoltage
- batteryPercent (optional estimate)
- tiltXDeg
- tiltYDeg
- tiltTimestampMs
- currentTimeUtc or currentTimeLocal
- timeSetAtMillis
- raText
- decText
- altText
- azText
- streamEnabled
- streamPeriodMs
- lastStreamMs
- messageActive
- messageText
- messageExpiresAtMs
- messagePersistent
- messageAwaitButtonsMask
- messageCorrelationId (optional)
- pendingButtonEvent
```

Notes:

* RA/Dec and Alt/Az may initially be stored as strings for display simplicity.
* Tilt should be stored numerically.
* Time may be stored as epoch plus local millis offset, or another simple ticking representation.
* The message fields support temporary or persistent operator messages sent from the Raspberry Pi.
* Button event fields support reporting user acknowledgement or interaction back over BLE.

---

## BLE design goals

BLE is intended for communication with a nearby Raspberry Pi.

Design priorities:

* simple to implement,
* robust,
* low traffic by default,
* easy to inspect and debug,
* no need for continuous notifications unless explicitly enabled.

The default mode should be **request/reply** rather than constant streaming.

---

## BLE architecture

Use the M5StickC as a **BLE peripheral / GATT server**.

The Raspberry Pi acts as the **BLE central / client**.

### Advertising name

Suggested device name:

* `M5-NexStar-Level`

Alternative names can be chosen later.

### Service layout

A single custom service is enough for the first version.

#### Custom service

Suggested UUIDs (example values; replace if desired with your own chosen UUID set):

* Service UUID: `7d91b000-8f3b-4b63-b6a4-5d1e6b7a1000`
* Command characteristic: `7d91b001-8f3b-4b63-b6a4-5d1e6b7a1000`
* Response characteristic: `7d91b002-8f3b-4b63-b6a4-5d1e6b7a1000`
* Status characteristic: `7d91b003-8f3b-4b63-b6a4-5d1e6b7a1000`

### Characteristics

#### 1. Command characteristic

Properties:

* Write
* Write Without Response (optional)

Purpose:

* Raspberry Pi sends commands to the M5StickC.

#### 2. Response characteristic

Properties:

* Read
* Notify

Purpose:

* M5StickC returns replies to commands,
* may also be used for optional streaming.

#### 3. Status characteristic

Properties:

* Read

Purpose:

* basic static snapshot of current device status,
* useful for debugging and quick inspection.

For simplicity, the first implementation could even use only **Command** + **Response**.

---

## BLE protocol

A lightweight text protocol is recommended for the first implementation.

Each command is an ASCII line.
Each response is an ASCII line.

This avoids unnecessary complexity and makes debugging easy with generic BLE tools.

### General rules

* commands are case-sensitive or case-insensitive by choice; case-insensitive is friendlier,
* fields are separated by spaces,
* one command per write,
* one response per reply,
* optional newline termination may be used consistently.

---

## BLE commands

### Message and user-interaction feature

A new BLE-driven message feature is supported.

Purpose:

* allow the Raspberry Pi to display short operator messages on the M5StickC,
* optionally keep a message on screen for a fixed duration or indefinitely,
* optionally wait for one or more button presses,
* report button events back to the Raspberry Pi.

This allows the M5StickC to act as a tiny operator display while still remaining a clinometer and status instrument.

### Message display model

A BLE message may:

* appear as a full-screen message screen, or
* temporarily overlay the current screen.

### Recommendation

For version 1, use a **full-screen message mode** while a message is active.

Reason:

* much simpler on the small display,
* easier to read outdoors,
* easier to implement,
* avoids layout complications.

When the message expires or is cancelled, the device returns to the previously selected normal screen.

### Message duration options

Supported duration modes:

* fixed number of seconds,
* infinite until explicitly replaced or cancelled.

### Button-wait behavior

A message may optionally declare interest in button presses.

That means:

* the message is shown,
* one or more buttons are considered valid responses,
* when the user presses a matching button, the device sends a BLE event,
* the message may either remain visible or be cleared depending on implementation policy.

### Recommendation

For version 1:

* pressing a watched button should emit an event,
* the message should remain visible unless its timeout expires or a cancel/replace command is received.

This keeps behavior predictable.

---

### Query commands

#### `PING`

Returns a simple acknowledgement.

Response example:

```text
OK PONG
```

#### `GET_TILT`

Returns current X and Y tilt in degrees.

Response example:

```text
TILT +0.42 -1.17
```

#### `GET_STATUS`

Returns a compact state summary.

Response example:

```text
STATUS SCREEN=ALTAZ BLE=1 STREAM=0 BAT=3.96
```

#### `GET_TIME`

Returns current displayed time.

Response example:

```text
TIME 2026-04-19T18:42:10Z
```

#### `GET_RADEC`

Returns current RA/Dec values.

Response example:

```text
RADEC 12:34:56 +07:08:09
```

#### `GET_ALTAZ`

Returns current Alt/Az values.

Response example:

```text
ALTAZ +43.2 181.7
```

---

### Update commands

#### `SHOW_MSG <duration> <text>`

Displays a message for a finite number of seconds or indefinitely.

Examples:

```text
SHOW_MSG 5 Moving altitude axis
SHOW_MSG INF Waiting for solar centering
```

Responses:

```text
OK MSG
```

Meaning:

* `5` means display for 5 seconds
* `INF` means display until replaced or cancelled

#### `SHOW_MSG_WAIT <duration> <buttons> <text>`

Displays a message and requests button-event reporting for one or more buttons.

Examples:

```text
SHOW_MSG_WAIT 10 M5 Press M5 to continue
SHOW_MSG_WAIT INF M5,A Waiting for user confirmation
SHOW_MSG_WAIT 15 ANY Stop motion if something looks wrong
```

Responses:

```text
OK MSG_WAIT
```

Button mask values can be:

* `M5` for the large front button
* `A` for the top/side power-related button
* `B` for the third free button
* comma-separated combinations such as `M5,A`
* `ANY` for any button

#### `CANCEL_MSG`

Cancels the current active message immediately.

Response:

```text
OK MSG_CANCEL
```

#### `GET_MSG`

Returns the current active message state.

Example responses:

```text
MSG NONE
MSG ACTIVE INF BUTTONS=M5 TEXT=Press M5 to continue
MSG ACTIVE 4 BUTTONS=NONE TEXT=Moving altitude axis
```

---

### Event reporting

Button presses relevant to BLE interaction should be sent back as asynchronous events via the Response characteristic using notifications, or returned by polling if notifications are disabled.

Recommended event format:

```text
EVENT BUTTON M5
EVENT BUTTON A
EVENT BUTTON B
```

If desired, events may later include a correlation id or message id, for example:

```text
EVENT BUTTON M5 MSG=42
```

This is optional in v1.

### Recommendation

Use notifications for button events, even if ordinary state queries are request/reply.

Reason:

* button presses are naturally asynchronous,
* the Raspberry Pi should not need to poll aggressively just to learn that a user pressed a button.

---

#### `SET_TIME <iso8601>`

Sets the current time.

Example:

```text
SET_TIME 2026-04-19T18:42:10Z
```

Response:

```text
OK TIME
```

#### `SET_RADEC <ra> <dec>`

Sets the current RA/Dec display fields.

Example:

```text
SET_RADEC 12:34:56 +07:08:09
```

Response:

```text
OK RADEC
```

#### `SET_ALTAZ <alt> <az>`

Sets the current Alt/Az display fields.

Example:

```text
SET_ALTAZ +43.2 181.7
```

Response:

```text
OK ALTAZ
```

---

### Optional streaming commands

These are recommended but optional in the first version.

#### `START_STREAM <period_ms>`

Enables periodic tilt notifications.

Example:

```text
START_STREAM 500
```

Meaning:

* send tilt update every 500 ms

Response:

```text
OK STREAM 500
```

Notification example:

```text
TILT +0.38 -1.12
```

#### `STOP_STREAM`

Disables streaming.

Response:

```text
OK STREAM 0
```

### Recommendation

Even if streaming is implemented, default state at boot should be:

* streaming disabled
* Raspberry Pi polls using `GET_TILT`

This is simpler and likely better for battery life.

---

## BLE status characteristic format

If the optional status characteristic is implemented, a compact single-line text is enough.

Example:

```text
SCREEN=TIME;BLE=1;BAT=3.96;STREAM=0
```

This is not required if `GET_STATUS` already exists.

---

## Error handling

Invalid commands should return a predictable error.

Example:

```text
ERR UNKNOWN_COMMAND
```

Examples of useful error replies:

```text
ERR BAD_ARGS
ERR BAD_TIME
ERR BAD_RADEC
ERR BAD_ALTAZ
```

---

## Screen definitions

## Message screen

This is a temporary full-screen mode shown while a BLE message is active.

Displays:

* message text, centered or wrapped,
* optional timeout indicator,
* optional hint showing which buttons are being watched,
* optional small BLE or battery indicator if space permits.

Behavior:

* overrides the normal screen display while active,
* does not disable BLE,
* does not stop IMU updates or other background state updates,
* on expiry or cancellation returns to the previously selected screen.

## 1. Clinometer screen

Displays:

* bubble level / target circles,
* X tilt angle,
* Y tilt angle,
* optional small BLE connection indicator,
* optional battery indicator.

This remains the most important screen for physical leveling.

## 2. Time screen

Displays:

* current time,
* optional date,
* optional BLE connection indicator,
* optional battery indicator.

The Pi is considered the authoritative source for setting time.

## 3. RA/Dec screen

Displays:

* RA value,
* Dec value,
* labels clearly visible on the small screen.

Formatting can initially be text-only.

## 4. Alt/Az screen

Displays:

* Alt value,
* Az value,
* labels clearly visible on the small screen.

Formatting can initially be text-only.

---

## Timing and update policy

### IMU sampling

Tilt should be updated continuously in the background at a modest internal rate.

Suggested starting rate:

* 10 Hz to 20 Hz internal IMU sampling

This does not mean BLE must transmit that often.

### Display refresh

Suggested display refresh:

* only as often as visually useful,
* e.g. 5 Hz to 10 Hz for the clinometer screen,
* slower for static text screens if desired.

### BLE

Suggested default:

* no automatic streaming,
* respond on demand to `GET_TILT`,
* optional low-rate streaming only when enabled by command.

---

## Battery-life strategy

Given the limited internal battery of the M5StickC, the project should favor low-duty-cycle communication.

Recommended policy:

* BLE advertising enabled,
* BLE connection supported,
* no constant tilt notifications by default,
* optional low-rate stream only during active alignment,
* screen brightness kept moderate,
* no Wi-Fi background activity.

This is one of the main reasons for choosing BLE-first for Raspberry Pi communication.

---

## Software architecture recommendation

Suggested modules:

### `imu/`

Responsible for:

* IMU reads
* tilt calculation
* optional calibration / zero offset

### `ble/`

Responsible for:

* BLE server setup
* advertising
* command parsing
* response generation
* optional streaming state

### `ui/`

Responsible for:

* current screen rendering
* button-driven screen changes
* simple icons / status indicators

### `model/`

Responsible for:

* shared runtime state
* synchronized access if needed

### `system/`

Responsible for:

* battery readout
* reboot / shutdown handling
* timekeeping support

---

## Suggested implementation phases

### Phase 1

* preserve demo code in `demo/`
* isolate current clinometer code into the new project
* implement multi-screen UI shell
* implement Clinometer / Time / RA-Dec / Alt-Az screens with placeholder values

### Phase 2

* add BLE peripheral / GATT server
* add `PING`, `GET_TILT`, `SET_TIME`, `SET_RADEC`, `SET_ALTAZ`
* verify commands work regardless of active screen

### Phase 3

* add `GET_STATUS`, `GET_TIME`, `GET_RADEC`, `GET_ALTAZ`
* add message commands: `SHOW_MSG`, `SHOW_MSG_WAIT`, `CANCEL_MSG`, `GET_MSG`
* add button-event notifications
* add BLE status icon / connection indicator on screen

### Phase 4

* add optional streaming commands
* optional third-button features
* optional tilt zeroing / brightness control
* optional polish and cleanup

---

## Acceptance criteria

The project can be considered successful when all of the following are true:

1. Device boots into the multi-screen application.
2. The M5 button cycles through Clinometer, Time, RA/Dec, and Alt/Az.
3. Top button short press reboots.
4. Top button long press shuts down / deep sleeps as expected.
5. BLE is visible and connectable while any screen is active.
6. Raspberry Pi can send `GET_TILT` and receive current tilt values.
7. Raspberry Pi can send `SET_TIME`, `SET_RADEC`, and `SET_ALTAZ`.
8. Updated values appear on the corresponding screens.
9. Clinometer continues to update tilt in the background even when not on the clinometer screen.
10. Raspberry Pi can send `SHOW_MSG` or `SHOW_MSG_WAIT` and the message appears on the device.
11. The device can cancel or expire messages correctly and return to the previous screen.
12. Button presses requested by a message can be reported back over BLE.
13. No Wi-Fi features are required.

---

## Open questions

1. Should RA/Dec and Alt/Az be stored and transported as formatted strings or as numeric values?

   * Recommendation: strings first, numeric later if needed.

2. Should time be shown in UTC or local time?

   * Recommendation: start with the exact value provided by the Raspberry Pi and document the convention.

3. Should the third button be unused in v1?

   * Recommendation: yes, unless brightness toggle or tilt zeroing is desired early.

4. Should optional streaming be in v1 or deferred?

   * Recommendation: defer unless polling proves inconvenient.

---

## Recommended v1 decisions

To keep scope under control, version 1 should use these choices:

* BLE request/reply for normal commands
* BLE notifications for asynchronous button events
* no Wi-Fi
* no camera control
* no third-button feature required outside optional message-wait interactions
* RA/Dec and Alt/Az stored as display strings
* one custom BLE service with command/response characteristics
* simple text protocol
* full-screen message mode for BLE operator messages

---

## Summary

This project turns the M5StickC into a compact BLE-enabled clinometer and status display for telescope alignment workflows.

The first version should focus on:

* a solid clinometer,
* four simple screens,
* a stable background BLE interface,
* button behavior consistent with the current demo base,
* low power consumption through BLE request/reply rather than continuous streaming.


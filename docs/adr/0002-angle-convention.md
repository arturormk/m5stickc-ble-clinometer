# Multi-Device IMU, Screen Axes, Pitch, and Roll Conventions

This note explains the coordinate and sign conventions for the supported M5Stack/M5Stick clinometer devices, especially:

* M5Stick Plus / M5StickC Plus-style rectangular devices.
* M5Stack Core2-style square devices.

The goal is cross-device behavior that feels coherent to users while preserving the practical astronomy-oriented convention:

```text
positive roll = telescope aperture side rises = altitude increases
```

The device is a clinometer with a bubble-level display. It is not primarily a raw IMU viewer. Therefore, reported pitch and roll are user-facing quantities whose signs are chosen to match the screen UI and telescope use, not necessarily to expose raw IMU Euler-angle signs.

---

## 1. General principle

Each device has three relevant coordinate frames:

1. **Hardware IMU frame**

   * Fixed by the device hardware.
   * Right-handed.
   * Used internally as the source of accelerometer/gyro data.

2. **Screen / UX frame**

   * Defined by how the user naturally looks at the display.
   * Also right-handed.
   * Used to define pitch and roll in a device-independent way.

3. **Telescope frame**

   * Defined by how the device is physically mounted on the optical tube assembly.
   * For the default astronomy use case, reported roll should correspond to telescope altitude.

The firmware should transform raw IMU measurements into the screen / UX frame, then apply the project’s pitch and roll sign conventions.

---

## 2. Common UX angle convention

For all supported devices, once a screen / UX frame has been defined:

```text
UX +X = screen right
UX +Y = screen up
UX +Z = out of the screen, toward the viewer
```

This is the natural right-handed screen coordinate frame:

```text
UX +X × UX +Y = UX +Z
```

The project uses the following user-facing pitch and roll conventions:

```text
reported_pitch = + mathematical_rotation_about(UX +X)
reported_roll  = - mathematical_rotation_about(UX +Y)
```

In words:

```text
positive pitch:
    top of the screen rises / moves toward the user

positive roll:
    right side of the screen rises / moves toward the user
```

The sign reversal for roll is intentional. A mathematically positive right-hand-rule rotation about UX `+Y` moves UX `+Z` toward UX `+X`, which makes the UX `+X` side go down. For telescope use we want the opposite: when the screen-right side is the aperture side, positive roll should mean the aperture side rises.

Therefore:

```text
positive roll = screen-right side rises
```

not:

```text
positive roll = mathematically positive rotation about screen-up
```

This should be treated as a feature, not a bug. The bubble-level display arrows are the user-facing contract.

---

## 3. M5Stick Plus / rectangular device convention

For the rectangular M5Stick-style device, the natural project orientation is:

```text
M5 button on the left
screen on the right
landscape display orientation
screen facing the user
```

In this orientation, according to the M5Stick IMU diagram:

```text
screen right = IMU +Y
screen up    = IMU -X
screen out   = IMU +Z
```

Therefore the UX frame is:

```text
UX +X = IMU +Y
UX +Y = IMU -X
UX +Z = IMU +Z
```

This is right-handed:

```text
UX +X × UX +Y = UX +Z
IMU +Y × IMU -X = IMU +Z
```

### 3.1 Pitch on the M5Stick Plus

Pitch is positive mathematical rotation about UX `+X`:

```text
reported_pitch = + rotation_about(UX +X)
```

For the M5Stick Plus:

```text
UX +X = IMU +Y
```

So conceptually:

```text
reported_pitch = + rotation_about(IMU +Y)
```

Physical meaning:

```text
reported_pitch > 0:
    top of the landscape screen rises
    bottom of the landscape screen falls
```

### 3.2 Roll on the M5Stick Plus

Roll is intentionally defined as negative mathematical rotation about UX `+Y`:

```text
reported_roll = - rotation_about(UX +Y)
```

For the M5Stick Plus:

```text
UX +Y = IMU -X
```

So:

```text
reported_roll = - rotation_about(IMU -X)
              = + rotation_about(IMU +X)
```

Physical meaning:

```text
reported_roll > 0:
    right/screen side rises
    left/M5-button side falls
```

Default telescope mounting:

```text
M5 button / left side = eyepiece side
screen-right side     = aperture side
```

Therefore:

```text
reported_roll > 0:
    aperture side rises
    telescope altitude increases
```

This is the main reason for the roll sign convention.

---

## 4. M5Stack Core2 / square device convention

For the square Core2-style device, use the screen’s natural portrait-like orientation shown in the device orientation diagram:

```text
screen right = IMU +X
screen up    = IMU +Y
screen out   = IMU +Z
```

Therefore the UX frame is simply:

```text
UX +X = IMU +X
UX +Y = IMU +Y
UX +Z = IMU +Z
```

This is right-handed:

```text
UX +X × UX +Y = UX +Z
IMU +X × IMU +Y = IMU +Z
```

The Core2 is square, so there may not be one universally obvious way to attach it to a telescope tube. That is acceptable. The important thing is that the clinometer behavior remains consistent on screen and across devices.

### 4.1 Pitch on the Core2

Pitch is positive mathematical rotation about UX `+X`, which is also IMU `+X`:

```text
reported_pitch = + rotation_about(UX +X)
reported_pitch = + rotation_about(IMU +X)
```

Under the right-hand rule, positive rotation about IMU `+X` moves:

```text
IMU +Y toward IMU +Z
```

Physical meaning:

```text
reported_pitch > 0:
    screen top rises / moves toward the user
    screen bottom falls / moves away from the user
```

This matches the normal UX notion of “pitch up”.

### 4.2 Roll on the Core2

For cross-device consistency, roll should use the same project convention as the M5Stick Plus:

```text
reported_roll = - rotation_about(UX +Y)
```

For the Core2:

```text
UX +Y = IMU +Y
```

Therefore:

```text
reported_roll = - rotation_about(IMU +Y)
```

A mathematically positive right-hand-rule rotation about IMU `+Y` would move:

```text
IMU +Z toward IMU +X
```

which makes the IMU `+X` / screen-right side go down.

But the project’s reported roll is sign-reversed:

```text
reported_roll > 0:
    screen-right side rises
```

This keeps the behavior consistent with the M5Stick Plus:

```text
positive roll = screen-right side rises
```

If the Core2 is mounted on a telescope such that the screen-right side points toward the aperture, then:

```text
reported_roll > 0 = aperture side rises = altitude increases
```

If the user mounts it differently, the reported roll still behaves consistently relative to the display arrows, but it may not equal telescope altitude unless the mounting convention matches.

---

## 5. Bubble-level display limitation

The bubble-level display assumes that the device screen plane is approximately horizontal, like a physical bubble level.

Therefore the supported clinometer use case is:

```text
device lying on top of the telescope tube or another approximately horizontal reference surface
screen facing upward / toward the user
```

The device should not try to support arbitrary side-mounted interpretations where, for example:

```text
rotation about UX +Z = telescope altitude
```

That would require the screen plane to be vertical. In that orientation, the bubble-level analogy breaks down because the bubble display is no longer representing a level surface in the intuitive way.

So the project should not contort the pitch/roll conventions to support side-mounted OTA use. The intended use is a top-mounted clinometer with the screen plane acting like a bubble level.

---

## 6. Cross-device consistency rule

The simplest cross-device rule is:

```text
Define UX axes from the display:
    UX +X = screen right
    UX +Y = screen up
    UX +Z = out of screen

Then report:
    pitch = + rotation about UX +X
    roll  = - rotation about UX +Y
```

This gives the same human-facing behavior on both devices:

```text
positive pitch:
    top of screen rises

positive roll:
    right side of screen rises
```

The mapping from UX axes to raw IMU axes is device-specific.

---

## 7. Device-specific mapping table

### M5Stick Plus / rectangular device

Natural project orientation:

```text
M5 button left
screen right
landscape display
```

Mapping:

```text
UX +X = IMU +Y
UX +Y = IMU -X
UX +Z = IMU +Z
```

Reported angles:

```text
reported_pitch = + rotation_about(UX +X)
               = + rotation_about(IMU +Y)

reported_roll  = - rotation_about(UX +Y)
               = - rotation_about(IMU -X)
               = + rotation_about(IMU +X)
```

### M5Stack Core2 / square device

Natural screen orientation:

```text
screen right = IMU +X
screen up    = IMU +Y
screen out   = IMU +Z
```

Mapping:

```text
UX +X = IMU +X
UX +Y = IMU +Y
UX +Z = IMU +Z
```

Reported angles:

```text
reported_pitch = + rotation_about(UX +X)
               = + rotation_about(IMU +X)

reported_roll  = - rotation_about(UX +Y)
               = - rotation_about(IMU +Y)
```

---

## 8. Recommended implementation structure

The firmware should avoid scattering sign fixes throughout the code. Instead, define one device-specific axis mapping and one shared UX convention.

Conceptually:

```text
raw IMU vector
    ↓
device-specific transform into UX frame
    ↓
compute pitch/roll in UX frame
    ↓
apply project sign convention:
    pitch = +pitch_about_UX_X
    roll  = -roll_about_UX_Y
```

Suggested conceptual configuration:

```text
DeviceProfile M5StickPlus:
    ux_x = imu_y
    ux_y = -imu_x
    ux_z = imu_z

DeviceProfile Core2:
    ux_x = imu_x
    ux_y = imu_y
    ux_z = imu_z
```

Then the shared reported angle convention is identical:

```text
reported_pitch = + rotation_about(ux_x)
reported_roll  = - rotation_about(ux_y)
```

---

## 9. Documentation wording

Suggested documentation:

> The clinometer reports user-facing pitch and roll, not raw IMU Euler angles. For every supported device, the firmware first defines a screen-aligned UX frame: UX `+X` is screen right, UX `+Y` is screen up, and UX `+Z` is out of the screen. Displayed pitch is the positive mathematical rotation about UX `+X`, so positive pitch means the top of the screen rises. Displayed roll is intentionally sign-reversed relative to mathematical rotation about UX `+Y`, so positive roll means the right side of the screen rises. This keeps the astronomy use case natural: when the screen-right side is mounted toward the telescope aperture, positive roll means positive telescope altitude.

For the M5Stick Plus:

```text
UX +X = IMU +Y
UX +Y = IMU -X
UX +Z = IMU +Z
```

For the M5Stack Core2:

```text
UX +X = IMU +X
UX +Y = IMU +Y
UX +Z = IMU +Z
```

---

## 10. Final design decision

The project should use the same reported-angle semantics across supported devices:

```text
pitch:
    positive mathematical rotation about screen right / UX +X

roll:
    negative mathematical rotation about screen up / UX +Y
```

This gives the user a consistent bubble-level experience:

```text
positive pitch = top of screen rises
positive roll  = right side of screen rises
```

For astronomy, the recommended mounting is any top-of-OTA mounting where:

```text
screen-right side = telescope aperture side
```

In that mounting:

```text
positive roll = aperture rises = altitude increases
```

The square Core2 device may not have one uniquely obvious physical mounting orientation, but this does not matter as long as the screen arrows and Bluetooth-reported values follow the same UX convention.


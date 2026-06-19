#!/usr/bin/env python3
"""Real-time 3D visualizer for the M5Stack BLE clinometer.

Usage:
    python tests/3d_model.py                   # auto-connect from conf, or interactive scan
    python tests/3d_model.py -d main           # connect by config name (device.main in conf)
    python tests/3d_model.py -d AA:BB:CC:DD:EE:FF  # connect by raw MAC
    python tests/3d_model.py --sim             # animated demo, no BLE
    python tests/3d_model.py -d main --model 2

Keys: 1/2/3/4 switch device model, Q/Esc quit.
"""

import argparse
import asyncio
import math
import os
import pathlib
import sys
import threading
from dataclasses import dataclass, field

import pygame
from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, QUIT, K_ESCAPE, K_q, K_1, K_2, K_3, K_4, K_c
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST,
    GL_MODELVIEW, GL_PROJECTION, GL_QUADS,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
    glBegin, glBlendFunc, glClear, glClearColor, glColor3f,
    glDisable, glEnable, glEnd, glVertex3f,
    glLoadIdentity, glMatrixMode, glPopMatrix, glPushMatrix,
    glRotatef, glTranslatef, glWindowPos2i,
)
from OpenGL.GLU import gluCylinder, gluDeleteQuadric, gluLookAt, gluNewQuadric, gluPerspective

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

# GLUT bitmap fonts — available if freeglut is installed (graceful fallback otherwise)
_GLUT_OK = False
try:
    from OpenGL.GLUT import glutInit, glutBitmapCharacter, GLUT_BITMAP_9_BY_15
    _GLUT_OK = True
except Exception:
    pass

# ── BLE constants (mirrors tests/conftest.py) ──────────────────────────────────
CMD_UUID      = "7d91b001-8f3b-4b63-b6a4-5d1e6b7a1000"
RESP_UUID     = "7d91b002-8f3b-4b63-b6a4-5d1e6b7a1000"
STREAM_MS     = 100   # firmware minimum is 100 ms → ~10 Hz

def _get_conf_path() -> pathlib.Path:
    if getattr(sys, 'frozen', False):
        local = pathlib.Path(sys.executable).parent / "m5ctl.conf"
        if local.is_file():
            return local
    else:
        project_root = pathlib.Path(__file__).resolve().parent.parent / ".m5ctl.conf"
        if project_root.is_file():
            return project_root
        tools_local = pathlib.Path(__file__).resolve().parent / "m5ctl.conf"
        if tools_local.is_file():
            return tools_local
    return pathlib.Path.home() / ".m5ctl.conf"


def _load_device_entries() -> tuple[dict[str, tuple[str, str | None]], str | None]:
    """Return (entries, default_name).

    entries      — {name: (mac, annotation)} for all device.NAME keys
    default_name — value of default_device key, or None
    """
    conf_file = _get_conf_path()
    if not conf_file.is_file():
        return {}, None
    entries: dict[str, tuple[str, str | None]] = {}
    default_name: str | None = None
    for raw in conf_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().split("#")[0].rstrip()
        if key.startswith("device."):
            name = key[len("device."):]
            if name:
                mac = val[:17]
                annotation = val[17:].strip() or None
                entries[name] = (mac, annotation)
        elif key == "default_device":
            default_name = val or None
    return entries, default_name


def _resolve_device(selector: str | None) -> str | None:
    if selector is not None:
        if len(selector) == 17 and selector.count(":") == 5:
            return selector
        entries, _ = _load_device_entries()
        devices = {name: mac for name, (mac, _) in entries.items()}
        if selector in devices:
            return devices[selector]
        print(f"error: device {selector!r} not found in config.", file=sys.stderr)
        return None

    env = os.environ.get("M5_BLE_ADDR")
    if env:
        return env

    entries, default_name = _load_device_entries()
    if default_name:
        devices = {name: mac for name, (mac, _) in entries.items()}
        if default_name in devices:
            return devices[default_name]
        print(f"warning: default_device {default_name!r} not found in config — ignored",
              file=sys.stderr)

    if entries:
        return next(iter(entries.values()))[0]
    return None

# ── Device models ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeviceModel:
    name: str
    w: float          # X half-dimension in OpenGL units (width / 2)
    h: float          # Y half-dimension (height / 2)
    d: float          # Z half-dimension (depth / 2)
    # pitch_axis: device-hardware UX-to-IMU mapping (ADR 0002), used only for
    # reconstructing the raw IMU vector shown in the HUD.
    #   'X'   (StickC Plus 2 landscape) → IMU ax = -guy,  ay =  gux,  az = guz
    #   'Y'   (Core2/CoreS3)            → IMU ax =  gux,  ay =  guy,  az = guz
    #   'NXY' (StickS3)                 → IMU ax = -gux,  ay = -guy,  az = guz
    pitch_axis: str   = 'Y'
    # GL rotation axes derived from the UX-to-model axis mapping for this device.
    # ux_x_gl: model-space axis vector corresponding to UX +X (screen right).
    # ux_neg_y_gl: model-space axis vector for UX −Y.
    #   Used directly for the '+Y' axis code because +Y means negative mathematical
    #   rotation about UX +Y (ADR 0002: roll = −rotation_about(UX +Y)), which equals
    #   a positive rotation about UX −Y.
    # M5StickC Plus 2 landscape: UX +X = model +Y, UX +Y = model −X
    #   → ux_x_gl=(0,1,0), ux_neg_y_gl=(1,0,0)
    # M5StickS3: same physical form factor and screen orientation as Plus 2
    #   → same ux_x_gl / ux_neg_y_gl; IMU axes differ (see pitch_axis='NXY')
    # Core2 / CoreS3: UX frame = model frame
    #   → ux_x_gl=(1,0,0), ux_neg_y_gl=(0,−1,0)
    ux_x_gl:     tuple = (1.0,  0.0, 0.0)
    ux_neg_y_gl: tuple = (0.0, -1.0, 0.0)
    # Camera eye position for gluLookAt (target = origin, up = GL +Z).
    # M5StickC: viewed from +X with slight −Y offset (long Y axis appears horizontal).
    # Core2/CoreS3: viewed from −Y with 15° rotation about Z (square portrait face visible).
    camera_eye: tuple = (6.5, -3.0, 5.0)
    # Screen inset on the +Z face.  All values are fractions of w or h.
    scr_x_offset: float = 0.0   # screen centre shift as fraction of w toward +X
    scr_y_offset: float = 0.0   # screen centre shift as fraction of h toward +Y
    scr_w_frac:   float = 0.88  # screen half-width  as fraction of w
    scr_h_frac:   float = 0.88  # screen half-height as fraction of h

# Physical mm → OpenGL units via /20.  Stick devices are portrait (Y is long axis).
# Plus 2 / S3 screen (~14 × 25 mm) sits toward the +Y end (top in portrait, away
# from the USB-C port) and is narrower than the body.
MODELS = [
    DeviceModel("M5StickC Plus 2", w=27.3/20, h=53.3/20, d=13.5/20,
                pitch_axis='X', ux_x_gl=(0.0, 1.0, 0.0), ux_neg_y_gl=(1.0, 0.0, 0.0),
                scr_y_offset=0.25, scr_w_frac=0.52, scr_h_frac=0.48),
    DeviceModel("M5Stack Core 2",  w=54.0/20, h=54.0/20, d=16.0/20,
                camera_eye=(1.8, -6.8, 5.0)),
    DeviceModel("M5Stack CoreS3",  w=54.0/20, h=54.0/20, d=13.0/20,
                camera_eye=(1.8, -6.8, 5.0)),
    # S3: same body/screen layout as Plus 2; IMU X and Y axes are both negated
    # relative to UX (UX +X = IMU −X, UX +Y = IMU −Y).
    DeviceModel("M5StickS3",       w=27.3/20, h=53.3/20, d=13.5/20,
                pitch_axis='NXY', ux_x_gl=(0.0, 1.0, 0.0), ux_neg_y_gl=(1.0, 0.0, 0.0),
                camera_eye=(6.5, -3.0, 5.0),
                scr_y_offset=0.25, scr_w_frac=0.52, scr_h_frac=0.48),
]

# Maps GET_BOARD response strings to MODELS indices.
BOARD_TO_MODEL: dict[str, int] = {
    "M5StickCPlus2": 0,
    "M5StickCPlus":  0,
    "M5StickC":      0,
    "M5StackCore2":  1,
    "M5StackCoreS3": 2,
    "M5Stack":       1,  # original Core falls back to Core2 geometry
    "M5StickS3":     3,
}

# ── Shared state between BLE thread and render thread ─────────────────────────

@dataclass
class TiltState:
    pitch:       float = 0.0
    roll:        float = 0.0
    g:           float = 1.0   # gravity magnitude in g units from TILT stream
    pitch_axis:  str   = '+X'  # axis code from GET_PITCHROLL
    roll_axis:   str   = '+Y'
    board_name:  str   = ""    # board string from GET_BOARD, e.g. "M5StickCPlus2"
    connected:   bool  = False
    error:       str   = ""
    retrying:    bool  = False
    retry_count: int   = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

# ── BLE worker (asyncio event loop in a daemon thread) ────────────────────────

class BleWorker:
    def __init__(self, address: str, state: TiltState) -> None:
        self._address          = address
        self._state            = state
        self._stop             = threading.Event()
        self._loop             = asyncio.new_event_loop()
        self._thread           = threading.Thread(target=self._thread_main, daemon=True)
        self._pitchroll_event: asyncio.Event | None = None
        self._board_event:     asyncio.Event | None = None

    def start(self) -> None:
        self._thread.start()

    def signal_stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _thread_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())

    async def _run(self) -> None:
        while not self._stop.is_set():
            client = BleakClient(self._address, timeout=10.0)
            try:
                last_exc = None
                for attempt in range(3):
                    with self._state.lock:
                        self._state.retrying = attempt > 0
                        self._state.retry_count = attempt
                    try:
                        await asyncio.wait_for(client.connect(), timeout=10.0)
                        last_exc = None
                        break
                    except (BleakError, asyncio.TimeoutError, OSError) as exc:
                        last_exc = exc
                        if attempt < 2 and not self._stop.is_set():
                            await asyncio.sleep(0.3 * (attempt + 1))
                if last_exc is not None:
                    raise last_exc

                with self._state.lock:
                    self._state.connected = True
                    self._state.retrying = False
                    self._state.retry_count = 0
                    self._state.error = ""

                await client.start_notify(RESP_UUID, self._on_notify)

                # Send GET_BOARD and GET_PITCHROLL sequentially so the firmware's
                # single-slot pendingBleResponse buffer isn't overwritten before the
                # main loop dispatches the first notification.
                self._board_event = asyncio.Event()
                await client.write_gatt_char(CMD_UUID, b"GET_BOARD", response=False)
                try:
                    await asyncio.wait_for(self._board_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                self._board_event = None

                self._pitchroll_event = asyncio.Event()
                await client.write_gatt_char(CMD_UUID, b"GET_PITCHROLL", response=False)
                try:
                    await asyncio.wait_for(self._pitchroll_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                self._pitchroll_event = None

                # STREAM start
                await client.write_gatt_char(
                    CMD_UUID, f"START_STREAM {STREAM_MS}".encode(), response=False
                )

                while not self._stop.is_set() and client.is_connected:
                    await asyncio.sleep(0.1)

                if client.is_connected:
                    await client.write_gatt_char(CMD_UUID, b"STOP_STREAM", response=False)

            except (BleakError, asyncio.TimeoutError, OSError) as exc:
                with self._state.lock:
                    self._state.connected = False
                    self._state.retrying = False
                    self._state.retry_count = 0
                    self._state.error = str(exc)

                if not self._stop.is_set():
                    await asyncio.sleep(3.0)

            finally:
                with self._state.lock:
                    self._state.connected = False
                    self._state.retrying = False
                try:
                    await client.disconnect()
                except Exception:
                    pass


    def _on_notify(self, _sender, data: bytearray) -> None:
        text = data.decode("utf-8", errors="replace").strip()
        if text.startswith("TILT "):
            parts = text.split()
            if len(parts) == 4:
                try:
                    p, r, g = float(parts[1]), float(parts[2]), float(parts[3])
                    with self._state.lock:
                        self._state.pitch = p
                        self._state.roll  = r
                        self._state.g     = g
                except ValueError:
                    pass
        elif text.startswith("BOARD "):
            name = text.split(None, 1)[1]
            with self._state.lock:
                self._state.board_name = name
            if self._board_event is not None:
                self._board_event.set()
        elif text.startswith("PITCHROLL "):
            _, axes = text.split(None, 1)
            parts = axes.split(",")
            valid = {"+X", "-X", "+Y", "-Y"}
            if len(parts) == 2 and parts[0] in valid and parts[1] in valid:
                with self._state.lock:
                    self._state.pitch_axis = parts[0]
                    self._state.roll_axis  = parts[1]
                if self._pitchroll_event is not None:
                    self._pitchroll_event.set()

# ── OpenGL drawing helpers ────────────────────────────────────────────────────

def draw_box(model: DeviceModel) -> None:
    """Draw a solid colored box for the device with a screen-face indicator."""
    w, h, d = model.w, model.h, model.d

    faces = [
        # (normal_axis, sign, color_rgb, vertices_ccw_from_outside)
        # +Z = screen face
        ([(+w, -h, +d), (+w, +h, +d), (-w, +h, +d), (-w, -h, +d)], (0.25, 0.65, 0.85)),
        # -Z = back
        ([(-w, -h, -d), (-w, +h, -d), (+w, +h, -d), (+w, -h, -d)], (0.20, 0.20, 0.22)),
        # +Y = top edge
        ([(-w, +h, -d), (-w, +h, +d), (+w, +h, +d), (+w, +h, -d)], (0.28, 0.42, 0.28)),
        # -Y = bottom edge
        ([(-w, -h, +d), (-w, -h, -d), (+w, -h, -d), (+w, -h, +d)], (0.20, 0.32, 0.20)),
        # +X = right edge
        ([(+w, -h, +d), (+w, -h, -d), (+w, +h, -d), (+w, +h, +d)], (0.40, 0.22, 0.22)),
        # -X = left edge
        ([(-w, -h, -d), (-w, -h, +d), (-w, +h, +d), (-w, +h, -d)], (0.30, 0.16, 0.16)),
    ]

    glBegin(GL_QUADS)
    for verts, color in faces:
        glColor3f(*color)
        for v in verts:
            glVertex3f(*v)
    glEnd()

    # Screen inset on +Z face
    scr_cx = model.scr_x_offset * w
    scr_cy = model.scr_y_offset * h
    sw     = model.scr_w_frac   * w
    sh     = model.scr_h_frac   * h
    glBegin(GL_QUADS)
    glColor3f(0.08, 0.08, 0.12)
    glVertex3f(scr_cx + sw, scr_cy - sh, +d + 0.001)
    glVertex3f(scr_cx + sw, scr_cy + sh, +d + 0.001)
    glVertex3f(scr_cx - sw, scr_cy + sh, +d + 0.001)
    glVertex3f(scr_cx - sw, scr_cy - sh, +d + 0.001)
    glEnd()


def _arrow(quad, length: float, shaft_r: float, head_r: float, head_len: float) -> None:
    """Draw a GLU cylinder arrow (shaft + cone) along +Z."""
    gluCylinder(quad, shaft_r, shaft_r, length, 10, 1)
    glTranslatef(0.0, 0.0, length)
    gluCylinder(quad, head_r, 0.0, head_len, 10, 1)
    glTranslatef(0.0, 0.0, -length)


def _rotate_z_toward(dx: float, dy: float, dz: float) -> None:
    """Rotate so that +Z faces the given axis-aligned unit vector."""
    if   dz >  0.5: pass
    elif dz < -0.5: glRotatef(180.0, 1.0, 0.0, 0.0)
    elif dx >  0.5: glRotatef( 90.0, 0.0, 1.0, 0.0)
    elif dx < -0.5: glRotatef(-90.0, 0.0, 1.0, 0.0)
    elif dy >  0.5: glRotatef(-90.0, 1.0, 0.0, 0.0)
    else:           glRotatef( 90.0, 1.0, 0.0, 0.0)


def draw_axes(model: DeviceModel, show_ux: bool = False) -> None:
    """Draw RGB arrows along the device's IMU or UX/screen axes."""
    scale   = max(model.w, model.h, model.d)
    length  = scale * 1.9
    shaft_r = scale * 0.06
    head_r  = scale * 0.14
    head_l  = scale * 0.25
    quad    = gluNewQuadric()

    if show_ux:
        ux_y = (-model.ux_neg_y_gl[0], -model.ux_neg_y_gl[1], -model.ux_neg_y_gl[2])
        axes: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = [
            ((0.9, 0.15, 0.15), model.ux_x_gl),    # UX +X  red
            ((0.15, 0.9, 0.15), ux_y),              # UX +Y  green
            ((0.15, 0.35, 0.9), (0.0, 0.0, 1.0)),  # UX +Z  blue
        ]
    else:
        # Derive IMU axis directions in GL model space from the UX↔IMU mapping.
        # 'X'   (Plus 2): IMU +X = UX −Y = ux_neg_y_gl,  IMU +Y = UX +X = ux_x_gl
        # 'NXY' (S3):     IMU +X = UX −X = −ux_x_gl,     IMU +Y = UX −Y = ux_neg_y_gl
        # 'Y'   (Core2):  IMU +X = UX +X = ux_x_gl,      IMU +Y = UX +Y = −ux_neg_y_gl
        if model.pitch_axis == 'X':
            imu_x: tuple = model.ux_neg_y_gl
            imu_y: tuple = model.ux_x_gl
        elif model.pitch_axis == 'NXY':
            imu_x = (-model.ux_x_gl[0], -model.ux_x_gl[1], -model.ux_x_gl[2])
            imu_y = model.ux_neg_y_gl
        else:
            imu_x = model.ux_x_gl
            imu_y = (-model.ux_neg_y_gl[0], -model.ux_neg_y_gl[1], -model.ux_neg_y_gl[2])
        axes = [
            ((0.9, 0.15, 0.15), imu_x),             # IMU +X  red
            ((0.15, 0.9, 0.15), imu_y),              # IMU +Y  green
            ((0.15, 0.35, 0.9), (0.0, 0.0, 1.0)),   # IMU +Z  blue
        ]

    for color, direction in axes:
        glColor3f(*color)
        glPushMatrix()
        _rotate_z_toward(*direction)
        _arrow(quad, length, shaft_r, head_r, head_l)
        glPopMatrix()

    gluDeleteQuadric(quad)


# ── Quaternion helpers ────────────────────────────────────────────────────────

def _quat_mul(q1: tuple, q2: tuple) -> tuple:
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
    )


def _quat_normalize(q: tuple) -> tuple:
    w, x, y, z = q
    n = math.sqrt(w*w + x*x + y*y + z*z)
    if n < 1e-12:
        return (1.0, 0.0, 0.0, 0.0)
    return (w/n, x/n, y/n, z/n)


def _quat_from_vecs(a: tuple, b: tuple) -> tuple:
    """Shortest-arc quaternion rotating unit vector a to unit vector b."""
    dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
    cx  = a[1]*b[2] - a[2]*b[1]
    cy  = a[2]*b[0] - a[0]*b[2]
    cz  = a[0]*b[1] - a[1]*b[0]
    w   = 1.0 + dot
    if w < 1e-6:
        # Anti-parallel: rotate 180° about any perpendicular axis.
        if abs(a[0]) < 0.9:
            px, py, pz = 0.0, -a[2], a[1]
        else:
            px, py, pz = a[2], 0.0, -a[0]
        n = math.sqrt(px*px + py*py + pz*pz)
        return (0.0, px/n, py/n, pz/n)
    return _quat_normalize((w, cx, cy, cz))


def _quat_to_axis_angle(q: tuple) -> tuple:
    """Return (ax, ay, az, angle_deg) suitable for glRotatef."""
    w, x, y, z = _quat_normalize(q)
    if w < 0:
        w, x, y, z = -w, -x, -y, -z
    w         = min(1.0, w)
    angle_rad = 2.0 * math.acos(w)
    s         = math.sqrt(max(0.0, 1.0 - w*w))
    if s < 1e-8:
        return (0.0, 0.0, 1.0, math.degrees(angle_rad))
    return (x/s, y/s, z/s, math.degrees(angle_rad))


# ── Renderer ──────────────────────────────────────────────────────────────────

class Renderer:
    WIDTH  = 900
    HEIGHT = 650

    def init(self) -> None:
        pygame.init()
        pygame.display.set_mode((self.WIDTH, self.HEIGHT), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("M5Stack 3D Clinometer Visualizer")

        glClearColor(0.07, 0.07, 0.10, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.WIDTH / self.HEIGHT, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

        if _GLUT_OK:
            glutInit()

        self._orient_q:  tuple        = (1.0, 0.0, 0.0, 0.0)
        self._prev_grav: tuple | None = None

    def handle_events(self) -> tuple[bool, int | None, bool]:
        new_model: int | None = None
        toggle_axes = False
        for event in pygame.event.get():
            if event.type == QUIT:
                return True, None, False
            if event.type == KEYDOWN:
                if event.key in (K_q, K_ESCAPE):
                    return True, None, False
                if event.key == K_1:
                    new_model = 0
                elif event.key == K_2:
                    new_model = 1
                elif event.key == K_3:
                    new_model = 2
                elif event.key == K_4:
                    new_model = 3
                elif event.key == K_c:
                    toggle_axes = True
        return False, new_model, toggle_axes

    def render(self, pitch, roll, g, connected, error, retrying, retry_count,
               demo, model, disconnecting=False, pitch_axis='+X', roll_axis='+Y',
               show_ux=False, board_name=""):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        # Camera position is model-specific (DeviceModel.camera_eye); target = origin,
        # up = GL +Z.  Each position is chosen to show the device's natural orientation
        # with a ~15° rotation about Z for depth perception.
        ex, ey, ez = model.camera_eye
        gluLookAt(ex, ey, ez,  0.0, 0.0, 0.0,  0.0, 0.0, 1.0)

        # Reconstruct UX gravity vector from TILT angles and axis codes.
        # Firmware uses atan2(component, cross-axis-magnitude), so component = g·sin(angle).
        alpha  = math.radians(pitch)
        beta   = math.radians(roll)
        sa, sb = math.sin(alpha), math.sin(beta)
        p_sign = +1.0 if pitch_axis[0] == '+' else -1.0
        r_sign = +1.0 if roll_axis[0]  == '+' else -1.0
        if pitch_axis[1] == 'X':
            # +X/-X pitch: atan2(±guy, …) = pitch  →  guy = ±g·sin(pitch)
            # -Y/+Y roll:  atan2(∓gux, …) = roll   →  gux = ∓g·sin(roll)
            guy_ux =  p_sign * g * sa
            gux_ux = -r_sign * g * sb
        else:
            # +Y/-Y pitch: atan2(∓gux, …) = pitch  →  gux = ∓g·sin(pitch)
            # +X/-X roll:  atan2(±guy, …) = roll   →  guy = ±g·sin(roll)
            gux_ux = -p_sign * g * sa
            guy_ux =  r_sign * g * sb
        guz_mag = math.sqrt(max(0.0, g*g - guy_ux*guy_ux - gux_ux*gux_ux))
        # Firmware uses sign(guz) to extend atan2 range past ±90°; angles beyond
        # ±90° only occur when guz < 0 (device past vertical).
        guz_ux = guz_mag if (abs(pitch) <= 90.0 and abs(roll) <= 90.0) else -guz_mag

        ux_y   = (-model.ux_neg_y_gl[0], -model.ux_neg_y_gl[1], -model.ux_neg_y_gl[2])
        gux_gl = gux_ux * model.ux_x_gl[0] + guy_ux * ux_y[0]
        guy_gl = gux_ux * model.ux_x_gl[1] + guy_ux * ux_y[1]
        g_len  = math.sqrt(gux_gl*gux_gl + guy_gl*guy_gl + guz_ux*guz_ux)
        new_grav = (gux_gl/g_len, guy_gl/g_len, guz_ux/g_len) if g_len > 1e-9 else (0.0, 0.0, 1.0)
        if self._prev_grav is None:
            self._orient_q = _quat_from_vecs(new_grav, (0.0, 0.0, 1.0))
        else:
            self._orient_q = _quat_normalize(_quat_mul(
                _quat_from_vecs(new_grav, self._prev_grav), self._orient_q
            ))
        self._prev_grav = new_grav
        ax, ay, az, angle = _quat_to_axis_angle(self._orient_q)
        if angle > 1e-6:
            glRotatef(angle, ax, ay, az)

        draw_box(model)
        draw_axes(model, show_ux)

        # HUD IMU vector: project UX gravity onto device IMU axes.
        if model.pitch_axis == 'X':
            # M5StickC Plus 2 landscape: UX +X = IMU +Y, UX +Y = IMU -X
            ax, ay, az = -guy_ux, gux_ux, guz_ux
        elif model.pitch_axis == 'NXY':
            # M5StickS3: UX +X = IMU -X, UX +Y = IMU -Y
            ax, ay, az = -gux_ux, -guy_ux, guz_ux
        else:
            # Core2 / CoreS3: UX frame = IMU frame
            ax, ay, az = gux_ux, guy_ux, guz_ux

        blink_on = (pygame.time.get_ticks() // 500) % 2 == 0
        if disconnecting:
            ble_status = "disconnecting..." if blink_on else ""
        elif demo:
            ble_status = "demo mode (no BLE)"
        elif connected:
            ble_status = "connected"
        elif retrying:
            ble_status = f"retrying ({retry_count}/3)..." if blink_on else ""
        elif error:
            ble_status = f"error: {error[:48]}"
        else:
            ble_status = "connecting..." if blink_on else ""

        hud_lines = [
            f"Pitch: {pitch:+7.2f}°  ({pitch_axis})   Roll: {roll:+7.2f}°  ({roll_axis})   g: {g:.2f}",
            f"accX: {ax:+.3f}   accY: {ay:+.3f}   accZ: {az:+.3f}",
            f"BLE: {ble_status}",
            f"BOARD (from firmware): {board_name or '(none)'}",
            f"Model (viewer): {model.name}   [1-4] switch  [C] {'UX' if show_ux else 'IMU'} axes  [Q] quit",
        ]
        self._draw_hud(hud_lines)

        pygame.display.flip()

    def _draw_hud(self, lines: list[str]) -> None:
        if not _GLUT_OK:
            return
        glDisable(GL_DEPTH_TEST)
        glColor3f(0.86, 0.86, 0.39)
        # glWindowPos2i uses window coordinates (origin = bottom-left); place text at top-left
        y = self.HEIGHT - 20
        for text in lines:
            glWindowPos2i(10, y)
            for ch in text:
                glutBitmapCharacter(GLUT_BITMAP_9_BY_15, ord(ch))
            y -= 20
        glEnable(GL_DEPTH_TEST)

    def model_changed(self, model: DeviceModel):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.WIDTH / self.HEIGHT, 0.1, 100.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        ex, ey, ez = model.camera_eye
        gluLookAt(ex, ey, ez, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)

    def apply_model(self, model: DeviceModel):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        ex, ey, ez = model.camera_eye
        gluLookAt(ex, ey, ez, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        self._prev_grav = None

    def quit(self) -> None:
        pygame.quit()


# ── Entry point ───────────────────────────────────────────────────────────────

def _scan_and_pick() -> str | None:
    """Scan for BLE devices, print a numbered list, return the chosen address."""
    async def _do_scan():
        print("Scanning for 5 seconds…", flush=True)
        results = await BleakScanner.discover(timeout=5.0, return_adv=True)
        return sorted(results.values(), key=lambda x: x[1].rssi or -999, reverse=True)

    pairs = asyncio.run(_do_scan())
    if not pairs:
        print("No BLE devices found.", file=sys.stderr)
        return None

    for i, (dev, adv) in enumerate(pairs, 1):
        name = dev.name or "(unknown)"
        rssi = adv.rssi or -999
        print(f"  {i})  {dev.address}  {rssi:4d} dBm  {name}")

    print()
    try:
        raw = input(f"Select device [1-{len(pairs)}]: ").strip()
        idx = int(raw) - 1
        if 0 <= idx < len(pairs):
            return pairs[idx][0].address
        print("Invalid selection.", file=sys.stderr)
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="3D orientation visualizer for M5Stack BLE clinometer"
    )
    parser.add_argument(
        "-d", "--device",
        default=None,
        metavar="ADDR_OR_NAME",
        help="BLE address or config name (e.g. 'main'). Names are listed by 'm5ctl list'.",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Run in simulator mode (no BLE, animated demo)",
    )
    parser.add_argument(
        "--model", type=int, choices=[1, 2, 3, 4], default=None, metavar="N",
        help="Device model: 1=Plus2, 2=Core2, 3=CoreS3, 4=StickS3. Auto-detected via GET_BOARD if omitted.",
    )
    args = parser.parse_args()

    demo_mode   = args.sim
    device_addr = None

    if not demo_mode:
        device_addr = _resolve_device(args.device)
        if not device_addr:
            print("No device configured. Starting interactive scan…")
            device_addr = _scan_and_pick()
        if not device_addr:
            print("No device selected.", file=sys.stderr)
            return

    state  = TiltState()
    worker: BleWorker | None = None

    if not demo_mode:
        worker = BleWorker(device_addr, state)  # type: ignore[arg-type]
        worker.start()

    renderer = Renderer()
    renderer.init()
    clock = pygame.time.Clock()

    auto_model    = not demo_mode and (not args.model)
    model_idx     = (args.model - 1) if args.model is not None else 0
    model         = MODELS[model_idx]
    board_applied = False
    running       = True
    show_ux       = False

    try:
        while running:
            quit_req, new_model, toggle_axes = renderer.handle_events()
            if quit_req:
                running = False
                continue
            if toggle_axes:
                show_ux = not show_ux
            if new_model is not None:
                model_idx = new_model
                model = MODELS[model_idx]
                renderer.apply_model(model)
                board_applied = True

            elif auto_model and not board_applied:
                with state.lock:
                    bn = state.board_name
                if bn:
                    model_idx = BOARD_TO_MODEL.get(bn, model_idx)
                    model = MODELS[model_idx]
                    renderer.apply_model(model)
                    board_applied = True

            with state.lock:
                pitch       = state.pitch
                roll        = state.roll
                g           = state.g
                pitch_axis  = state.pitch_axis
                roll_axis   = state.roll_axis
                connected   = state.connected
                error       = state.error
                retrying    = state.retrying
                retry_count = state.retry_count
                board_name  = state.board_name

            if demo_mode:
                t     = pygame.time.get_ticks() / 1000.0
                pitch = 25.0 * math.sin(t * 0.6)
                roll  = 18.0 * math.cos(t * 0.4)
                g     = 1.0

            renderer.render(pitch, roll, g, connected, error, retrying, retry_count, demo_mode, model,
                            pitch_axis=pitch_axis, roll_axis=roll_axis, show_ux=show_ux,
                            board_name=board_name)

            clock.tick(60)
    except KeyboardInterrupt:
        running = False

    if worker:
        worker.signal_stop()
        while worker.is_alive():
            with state.lock:
                pitch       = state.pitch
                roll        = state.roll
                g           = state.g
                pitch_axis  = state.pitch_axis
                roll_axis   = state.roll_axis
                connected   = state.connected
                error       = state.error
                retrying    = state.retrying
                retry_count = state.retry_count
            renderer.render(
                pitch, roll, g, connected, error, retrying, retry_count,
                demo_mode, model, disconnecting=True,
                pitch_axis=pitch_axis, roll_axis=roll_axis, show_ux=show_ux,
            )
            pygame.event.pump()
            clock.tick(30)
        worker.stop()
    renderer.quit()


if __name__ == "__main__":
    main()

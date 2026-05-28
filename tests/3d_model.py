#!/usr/bin/env python3
"""Real-time 3D visualizer for the M5Stack BLE clinometer.

Usage:
    python tests/3d_model.py                          # demo mode (animated)
    python tests/3d_model.py --device AA:BB:CC:DD:EE:FF
    python tests/3d_model.py --device AA:BB:CC:DD:EE:FF --model 2

Keys: 1/2/3 switch device model, Q/Esc quit.
"""

import argparse
import asyncio
import math
import os
import pathlib
import threading
from dataclasses import dataclass, field

import pygame
from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, QUIT, K_ESCAPE, K_q, K_1, K_2, K_3
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

_CONF_FILE = pathlib.Path(__file__).parent.parent / ".m5ctl.conf"


def _load_conf_addr() -> str | None:
    if not _CONF_FILE.is_file():
        return None
    for raw in _CONF_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            if key.strip() == "device":
                return val.strip() or None
    return None

# ── Device models ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeviceModel:
    name: str
    w: float          # X half-dimension in OpenGL units (width / 2)
    h: float          # Y half-dimension (height / 2)
    d: float          # Z half-dimension (depth / 2)
    # 'X' → M5StickC Plus / Plus2: IMU X runs along the physical long axis;
    #        pitch=atan2(-ax,az), roll=atan2(ay,az)
    # 'Y' → Core2, CoreS3, others: IMU Y runs along the physical long axis;
    #        pitch=atan2(ay,az),  roll=atan2(-ax,az)
    pitch_axis: str   = 'Y'
    # Screen inset on the +Z face.  All values are fractions of w or h.
    scr_x_offset: float = 0.0   # screen centre shift as fraction of w toward +X
    scr_y_offset: float = 0.0   # screen centre shift as fraction of h toward +Y
    scr_w_frac:   float = 0.88  # screen half-width  as fraction of w
    scr_h_frac:   float = 0.88  # screen half-height as fraction of h

# Physical mm → OpenGL units via /20.  Plus 2 is portrait (Y is long axis).
# Plus 2 screen (~14 × 25 mm) sits toward the +Y end (top in portrait, away
# from the USB-C port) and is narrower than the body.
MODELS = [
    DeviceModel("M5StickC Plus 2", w=27.3/20, h=53.3/20, d=13.5/20,
                pitch_axis='X', scr_y_offset=0.25, scr_w_frac=0.52, scr_h_frac=0.48),
    DeviceModel("M5Stack Core 2",  w=54.0/20, h=54.0/20, d=16.0/20),
    DeviceModel("M5Stack CoreS3",  w=54.0/20, h=54.0/20, d=13.0/20),
]

# ── Shared state between BLE thread and render thread ─────────────────────────

@dataclass
class TiltState:
    pitch:       float = 0.0
    roll:        float = 0.0
    g:           float = 1.0   # gravity magnitude in g units from TILT stream
    connected:   bool  = False
    error:       str   = ""
    retrying:    bool  = False
    retry_count: int   = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

# ── BLE worker (asyncio event loop in a daemon thread) ────────────────────────

class BleWorker:
    def __init__(self, address: str, state: TiltState) -> None:
        self._address = address
        self._state   = state
        self._stop    = threading.Event()
        self._loop    = asyncio.new_event_loop()
        self._thread  = threading.Thread(target=self._thread_main, daemon=True)

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
                last_exc: Exception | None = None
                for attempt in range(3):
                    with self._state.lock:
                        self._state.retrying    = attempt > 0
                        self._state.retry_count = attempt
                    try:
                        await client.connect()
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        if attempt < 2 and not self._stop.is_set():
                            await asyncio.sleep(0.3 * (attempt + 1))
                if last_exc is not None:
                    raise last_exc
                with self._state.lock:
                    self._state.connected    = True
                    self._state.retrying     = False
                    self._state.retry_count  = 0
                    self._state.error        = ""
                await client.start_notify(RESP_UUID, self._on_notify)
                await client.write_gatt_char(
                    CMD_UUID, f"START_STREAM {STREAM_MS}".encode(), response=False
                )
                while not self._stop.is_set() and client.is_connected:
                    await asyncio.sleep(0.1)
                if client.is_connected:
                    await client.write_gatt_char(CMD_UUID, b"STOP_STREAM", response=False)
            except Exception as exc:
                with self._state.lock:
                    self._state.connected    = False
                    self._state.retrying     = False
                    self._state.retry_count  = 0
                    self._state.error        = str(exc)
                if not self._stop.is_set():
                    await asyncio.sleep(3.0)
            finally:
                with self._state.lock:
                    self._state.connected = False
                    self._state.retrying  = False
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


def draw_axes(model: DeviceModel) -> None:
    """Draw RGB arrows along the device's X, Y, Z axes."""
    scale   = max(model.w, model.h, model.d)
    length  = scale * 1.9
    shaft_r = scale * 0.06
    head_r  = scale * 0.14
    head_l  = scale * 0.25
    quad    = gluNewQuadric()

    # X axis — red
    glColor3f(0.9, 0.15, 0.15)
    glPushMatrix()
    glRotatef(90.0, 0.0, 1.0, 0.0)
    _arrow(quad, length, shaft_r, head_r, head_l)
    glPopMatrix()

    # Y axis — green
    glColor3f(0.15, 0.9, 0.15)
    glPushMatrix()
    glRotatef(-90.0, 1.0, 0.0, 0.0)
    _arrow(quad, length, shaft_r, head_r, head_l)
    glPopMatrix()

    # Z axis — blue
    glColor3f(0.15, 0.35, 0.9)
    glPushMatrix()
    _arrow(quad, length, shaft_r, head_r, head_l)
    glPopMatrix()

    # Axis labels (short colored lines for X/Y/Z tips)
    gluDeleteQuadric(quad)


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

    def handle_events(self) -> tuple[bool, int | None]:
        new_model: int | None = None
        for event in pygame.event.get():
            if event.type == QUIT:
                return True, None
            if event.type == KEYDOWN:
                if event.key in (K_q, K_ESCAPE):
                    return True, None
                if event.key == K_1:
                    new_model = 0
                elif event.key == K_2:
                    new_model = 1
                elif event.key == K_3:
                    new_model = 2
        return False, new_model

    def render(
        self,
        pitch: float,
        roll: float,
        g: float,
        connected: bool,
        error: str,
        retrying: bool,
        retry_count: int,
        demo: bool,
        model: DeviceModel,
        disconnecting: bool = False,
    ) -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        # Camera above-right with Z as the up direction.  The X offset is large
        # relative to Y so the device's long Y axis appears nearly horizontal
        # (~15° from horizontal).  Reducing the X/Y ratio would tilt the long
        # axis back toward vertical (harder to see orientation).
        gluLookAt(6.5, -3.0, 5.0,  0.0, 0.0, 0.0,  0.0, 0.0, 1.0)

        # Apply device orientation: pitch around Y, roll around X.
        glRotatef(pitch, 0.0, 1.0, 0.0)
        glRotatef(roll,  1.0, 0.0, 0.0)

        draw_box(model)
        draw_axes(model)

        # Reconstruct acceleration vector from TILT <pitch> <roll> <g>.
        # Exact inverse of the firmware's atan2 formulas; see README.md for derivation.
        # D = sqrt(cos²β + sin²β·cos²α)  where α=pitch, β=roll (both in radians)
        alpha = math.radians(pitch)
        beta  = math.radians(roll)
        D = math.sqrt(math.cos(beta)**2 + math.sin(beta)**2 * math.cos(alpha)**2)
        if D < 1e-9:
            ax = ay = az = 0.0
        elif model.pitch_axis == 'X':
            # M5StickC Plus / Plus2: pitch=atan2(-ax,az), roll=atan2(ay,az)
            ax = -g * math.sin(alpha) * math.cos(beta)  / D
            ay =  g * math.sin(beta)  * math.cos(alpha) / D
            az =  g * math.cos(alpha) * math.cos(beta)  / D
        else:
            # Core2, CoreS3, others: pitch=atan2(ay,az), roll=atan2(-ax,az)
            ax = -g * math.sin(beta)  * math.cos(alpha) / D
            ay =  g * math.sin(alpha) * math.cos(beta)  / D
            az =  g * math.cos(alpha) * math.cos(beta)  / D

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
            f"Pitch: {pitch:+7.2f}°   Roll: {roll:+7.2f}°   g: {g:.2f}",
            f"accX: {ax:+.3f}   accY: {ay:+.3f}   accZ: {az:+.3f}",
            f"BLE: {ble_status}",
            f"Model: {model.name}   [1/2/3] switch  [Q] quit",
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

    def quit(self) -> None:
        pygame.quit()


# ── Entry point ───────────────────────────────────────────────────────────────

def _scan_and_pick() -> str | None:
    """Scan for BLE devices, print a numbered list, return the chosen address."""
    import sys

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
        "--device", default=None, metavar="ADDR",
        help="BLE address to connect (env M5_BLE_ADDR or .m5ctl.conf also work; omit to scan)",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Run in simulator mode (no BLE, animated demo)",
    )
    parser.add_argument(
        "--model", type=int, choices=[1, 2, 3], default=1, metavar="N",
        help="Starting device model: 1=Plus2, 2=Core2, 3=CoreS3",
    )
    args = parser.parse_args()

    import sys
    demo_mode   = args.sim
    device_addr = None

    if not demo_mode:
        device_addr = args.device or os.environ.get("M5_BLE_ADDR") or _load_conf_addr()
        if device_addr is None:
            device_addr = _scan_and_pick()
            if device_addr is None:
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

    model_idx = args.model - 1
    model     = MODELS[model_idx]
    running   = True

    while running:
        quit_req, new_model = renderer.handle_events()
        if quit_req:
            running = False
            continue
        if new_model is not None:
            model_idx = new_model
            model     = MODELS[model_idx]

        with state.lock:
            pitch       = state.pitch
            roll        = state.roll
            g           = state.g
            connected   = state.connected
            error       = state.error
            retrying    = state.retrying
            retry_count = state.retry_count

        if demo_mode:
            t     = pygame.time.get_ticks() / 1000.0
            pitch = 25.0 * math.sin(t * 0.6)
            roll  = 18.0 * math.cos(t * 0.4)
            g     = 1.0

        renderer.render(pitch, roll, g, connected, error, retrying, retry_count, demo_mode, model)
        clock.tick(60)

    if worker:
        worker.signal_stop()
        while worker.is_alive():
            with state.lock:
                pitch       = state.pitch
                roll        = state.roll
                g           = state.g
                connected   = state.connected
                error       = state.error
                retrying    = state.retrying
                retry_count = state.retry_count
            renderer.render(
                pitch, roll, g, connected, error, retrying, retry_count,
                demo_mode, model, disconnecting=True,
            )
            pygame.event.pump()
            clock.tick(30)
        worker.stop()
    renderer.quit()


if __name__ == "__main__":
    main()

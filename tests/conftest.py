"""Shared BLE session helper and pytest fixtures."""

import asyncio
import inspect
import os
import pathlib
import sys
from typing import ClassVar

import pytest
from bleak import BleakClient, BleakError
from bleak.exc import BleakDeviceNotFoundError

CONNECT_TIMEOUT = 10.0
CONNECT_RETRIES = 3
CMD_UUID  = "7d91b001-8f3b-4b63-b6a4-5d1e6b7a1000"
RESP_UUID = "7d91b002-8f3b-4b63-b6a4-5d1e6b7a1000"

_CONF_FILE = pathlib.Path(__file__).parent.parent / ".m5ctl.conf"


def _load_device_addr() -> str | None:
    if not _CONF_FILE.is_file():
        return None
    entries: dict[str, str] = {}  # name → mac
    default_name: str | None = None
    for raw in _CONF_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().split("#")[0].rstrip()
        if key == "device":
            # Legacy single-device format.
            return val or None
        if key.startswith("device."):
            name = key[len("device."):]
            if name:
                entries[name] = val[:17]  # MAC is always the first 17 chars
        elif key == "default_device":
            default_name = val or None
    if default_name and default_name in entries:
        return entries[default_name]
    if entries:
        return next(iter(entries.values()))
    return None


def _resolve_device_addr(config) -> str | None:
    return (
        config.getoption("--device")
        or os.environ.get("M5_BLE_ADDR")
        or _load_device_addr()
    )


def pytest_configure(config):
    global CONNECT_TIMEOUT, CONNECT_RETRIES
    t = config.getoption("--ble-timeout", default=None, skip=True)
    r = config.getoption("--ble-retries", default=None, skip=True)
    if t is not None:
        CONNECT_TIMEOUT = t
    if r is not None:
        CONNECT_RETRIES = r
    config.addinivalue_line(
        "markers",
        "ble_reconnect: test requires a real BLE disconnect/reconnect cycle; "
        "skipped automatically when --ble-keep-alive is active",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--device", default=None, metavar="ADDR",
        help="BLE address of the M5StickC device (env M5_BLE_ADDR or .m5ctl.conf also work)",
    )
    parser.addoption(
        "--ble-timeout", type=float, default=None, metavar="SECS",
        help="BLE connection timeout in seconds (default 10.0; increase for Windows/Core2)",
    )
    parser.addoption(
        "--ble-retries", type=int, default=None, metavar="N",
        help="BLE connection retry count (default 3)",
    )
    parser.addoption(
        "--ble-keep-alive", action="store_true", default=False,
        help="Reuse one BLE connection per test module instead of connecting per-test "
             "(reduces overhead on Windows / Core2; auto-reconnects on drops)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ble-keep-alive", default=False):
        return

    # Give every async test a module-scoped event loop so it shares the loop
    # with the _ble_keep_alive fixture and can safely reuse asyncio objects.
    ka_marker = pytest.mark.asyncio(loop_scope="module")
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(ka_marker, append=False)

    # Within each module move ble_reconnect tests to the end so all
    # keep-alive tests run together before the skipped reconnect ones.
    from collections import OrderedDict
    buckets: OrderedDict = OrderedDict()
    for item in items:
        mod = item.module.__name__
        if mod not in buckets:
            buckets[mod] = {"normal": [], "reconnect": []}
        key = "reconnect" if item.get_closest_marker("ble_reconnect") else "normal"
        buckets[mod][key].append(item)
    items[:] = []
    for b in buckets.values():
        items.extend(b["normal"])
        items.extend(b["reconnect"])


@pytest.fixture(scope="session")
def device_addr(pytestconfig):
    addr = _resolve_device_addr(pytestconfig)
    if not addr:
        pytest.skip("No device configured — set M5_BLE_ADDR, create .m5ctl.conf, or pass --device ADDR")
    return addr


@pytest.fixture(autouse=True)
def _ble_skip_reconnect(request):
    """Skip ble_reconnect-marked tests when --ble-keep-alive is active.

    These tests verify behaviour that depends on a real disconnect/reconnect
    (e.g. the newline sticky-flag resetting).  Reconnects are intentionally
    avoided in keep-alive mode, so there is nothing useful to assert.
    """
    if (
        request.config.getoption("--ble-keep-alive", default=False)
        and request.node.get_closest_marker("ble_reconnect")
    ):
        pytest.skip("requires reconnect — not applicable in --ble-keep-alive mode")


@pytest.fixture(scope="module", autouse=True)
async def _ble_keep_alive(request, pytestconfig):
    """When --ble-keep-alive is set, open one BLE connection per module and share it
    across all tests via BleSession._shared, reconnecting automatically on drops."""
    if not request.config.getoption("--ble-keep-alive", default=False):
        yield
        return
    # Only activate for modules that actually have BLE tests (use device_addr).
    has_ble_tests = any(
        "device_addr" in getattr(item, "fixturenames", ())
        for item in request.session.items
        if item.module is request.module
    )
    if not has_ble_tests:
        yield
        return
    addr = _resolve_device_addr(pytestconfig)
    if not addr:
        pytest.skip("No device configured — needed for --ble-keep-alive")
    session = BleSession(addr)
    await session.__aenter__()
    BleSession._shared = session
    try:
        yield
    finally:
        BleSession._shared = None
        await session.__aexit__(None, None, None)


class BleSession:
    """A connected BLE session supporting multiple sequential commands.

    Usage::

        async with BleSession(addr) as s:
            resp = await s.send("PING")          # → "OK PONG"
            raw  = await s.send_raw(b"PING\\n")  # → b"OK PONG\\n"
    """

    _shared: ClassVar["BleSession | None"] = None

    def __init__(self, address: str, timeout: float | None = None, retries: int | None = None):
        self._address = address
        self._timeout = timeout if timeout is not None else CONNECT_TIMEOUT
        self._retries = retries if retries is not None else CONNECT_RETRIES
        self._client: BleakClient | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._borrowed = False

    async def _do_connect(self) -> None:
        """Connect, using the BlueZ D-Bus cache on Linux to skip re-scanning.

        On Linux/BlueZ, once a device disconnects it may stop advertising, so a
        fresh BleakScanner.find_device_by_address() call never finds it again.
        dangerous_use_bleak_cache=True uses BlueZ's cached object path instead.
        On a cold start (no cache entry yet) it falls back to a normal scan.
        """
        if sys.platform == "linux":
            try:
                await self._client.connect(dangerous_use_bleak_cache=True)
                return
            except BleakDeviceNotFoundError:
                # No cache entry yet — recreate client and do a full scan.
                self._client = BleakClient(self._address, timeout=self._timeout)
        await self._client.connect()

    async def __aenter__(self) -> "BleSession":
        if BleSession._shared is not None and BleSession._shared is not self:
            # Keep-alive mode: borrow the module's shared connection.
            self._client = BleSession._shared._client
            self._queue  = BleSession._shared._queue
            self._borrowed = True
            await self._flush_pipeline()  # stop stream + drain all stale responses
            return self
        self._borrowed = False
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                self._client = BleakClient(self._address, timeout=self._timeout)
                await self._do_connect()
                await self._client.start_notify(RESP_UUID, self._on_notify)
                return self
            except BleakError as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def __aexit__(self, *_) -> None:
        if self._borrowed:
            await self._drain()  # light cleanup; _flush_pipeline in the next __aenter__ does the heavy work
            return
        if self._client:
            await self._client.disconnect()

    def _on_notify(self, _, data: bytearray) -> None:
        self._queue.put_nowait(bytes(data))

    async def _flush_pipeline(self) -> None:
        """Stop any running stream and flush all stale responses.

        Sends STOP_STREAM (stops any active stream) followed by PING (pipeline
        fence).  Because the device processes commands in order, OK PONG is
        guaranteed to arrive *after* all prior responses — including unconsumed
        send_no_wait responses from the previous test.  Draining until OK PONG
        therefore reliably empties the queue without relying on timing heuristics.
        """
        try:
            await self._client.write_gatt_char(CMD_UUID, b"STOP_STREAM", response=False)
            await self._client.write_gatt_char(CMD_UUID, b"PING", response=False)
        except BleakError:
            return
        deadline = asyncio.get_event_loop().time() + 3.0
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._queue.get(), remaining)
                if raw.decode("utf-8", errors="replace").strip() == "OK PONG":
                    break
            except asyncio.TimeoutError:
                break
        # Drain any items that arrived concurrently with OK PONG
        await self._drain()

    async def _drain(self) -> None:
        """Discard all notifications currently sitting in the queue (instant)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _reconnect(self) -> None:
        """Re-establish the BLE connection after a drop."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                self._client = BleakClient(self._address, timeout=self._timeout)
                await self._do_connect()
                await self._client.start_notify(RESP_UUID, self._on_notify)
                return
            except BleakError as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def _reconnect_shared(self) -> None:
        """Reconnect the shared session and refresh this instance's client reference."""
        await BleSession._shared._reconnect()  # type: ignore[union-attr]
        self._client = BleSession._shared._client  # type: ignore[union-attr]
        self._queue  = BleSession._shared._queue   # type: ignore[union-attr]

    async def recv_raw(self, timeout: float = 5.0) -> bytes:
        """Wait for the next BLE notification and return it as raw bytes."""
        return await asyncio.wait_for(self._queue.get(), timeout)

    async def recv(self, timeout: float = 5.0) -> str:
        """Wait for the next notification and return it decoded and stripped."""
        raw = await self.recv_raw(timeout)
        return raw.decode("utf-8", errors="replace").rstrip("\r\n ")

    async def recv_matching(self, prefix: str, skip: int = 8, timeout: float = 5.0) -> str:
        """Return the first notification starting with *prefix*, skipping others.

        Useful when collecting from a stream where in-flight TILT packets may
        arrive before the command response.
        """
        for _ in range(skip + 1):
            msg = await self.recv(timeout)
            if msg.startswith(prefix):
                return msg
        raise AssertionError(
            f"No notification starting with {prefix!r} within {skip + 1} attempts"
        )

    async def send_raw(self, cmd_bytes: bytes, timeout: float = 5.0) -> bytes:
        """Write *cmd_bytes* to the command characteristic, return the raw notify bytes."""
        try:
            await self._client.write_gatt_char(CMD_UUID, cmd_bytes, response=False)
        except BleakError:
            if not self._borrowed:
                raise
            await self._reconnect_shared()
            await self._client.write_gatt_char(CMD_UUID, cmd_bytes, response=False)
        return await self.recv_raw(timeout)

    async def send(self, cmd: str, newline: bool = False, timeout: float = 5.0) -> str:
        """Send a string command and return the decoded, stripped response string.

        Skips unsolicited EVENT notifications that may arrive asynchronously
        between commands (e.g. EVENT SCREEN when SHOW_MSG changes the active
        screen).  A single deadline spans all skipped notifications so the
        total wait never exceeds *timeout* seconds.
        """
        suffix = "\n" if newline else ""
        cmd_bytes = (cmd + suffix).encode()
        try:
            await self._client.write_gatt_char(CMD_UUID, cmd_bytes, response=False)
        except BleakError:
            if not self._borrowed:
                raise
            await self._reconnect_shared()
            await self._client.write_gatt_char(CMD_UUID, cmd_bytes, response=False)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"No command response within {timeout}s"
                    " (only EVENT notifications received)"
                )
            raw = await asyncio.wait_for(self._queue.get(), remaining)
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n ")
            if not text.startswith("EVENT "):
                return text

    async def send_no_wait(self, cmd: str) -> None:
        """Write a command without consuming a response notification."""
        try:
            await self._client.write_gatt_char(CMD_UUID, cmd.encode(), response=False)
        except BleakError:
            if not self._borrowed:
                raise
            await self._reconnect_shared()
            await self._client.write_gatt_char(CMD_UUID, cmd.encode(), response=False)

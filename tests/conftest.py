"""Shared BLE session helper and pytest fixtures."""

import asyncio
import os
import pathlib

import pytest
from bleak import BleakClient

CONNECT_TIMEOUT = 10.0
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


def pytest_addoption(parser):
    parser.addoption(
        "--device", default=None, metavar="ADDR",
        help="BLE address of the M5StickC device (env M5_BLE_ADDR or .m5ctl.conf also work)",
    )


@pytest.fixture(scope="session")
def device_addr(pytestconfig):
    addr = (
        pytestconfig.getoption("--device")
        or os.environ.get("M5_BLE_ADDR")
        or _load_device_addr()
    )
    if not addr:
        pytest.skip("No device configured — set M5_BLE_ADDR, create .m5ctl.conf, or pass --device ADDR")
    return addr


class BleSession:
    """A connected BLE session supporting multiple sequential commands.

    Usage::

        async with BleSession(addr) as s:
            resp = await s.send("PING")          # → "OK PONG"
            raw  = await s.send_raw(b"PING\\n")  # → b"OK PONG\\n"
    """

    def __init__(self, address: str, timeout: float = CONNECT_TIMEOUT):
        self._address = address
        self._timeout = timeout
        self._client: BleakClient | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def __aenter__(self) -> "BleSession":
        self._client = BleakClient(self._address, timeout=self._timeout)
        await self._client.connect()
        await self._client.start_notify(RESP_UUID, self._on_notify)
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.disconnect()

    def _on_notify(self, _, data: bytearray) -> None:
        self._queue.put_nowait(bytes(data))

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
        await self._client.write_gatt_char(CMD_UUID, (cmd + suffix).encode(), response=False)
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
        await self._client.write_gatt_char(CMD_UUID, cmd.encode(), response=False)

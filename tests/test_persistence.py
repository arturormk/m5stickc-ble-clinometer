"""Persistence tests: PERSIST / PERSIST CLEAR / PERSIST RESTORE / PERSIST READ / REBOOT.

These tests write to the on-device NVM (ESP32 NVS flash) and therefore cause
flash wear.  They are excluded from the default pytest run via --ignore in
pyproject.toml.  Run explicitly when needed::

    pytest tests/test_persistence.py
    pytest tests/test_persistence.py --device AA:BB:CC:DD:EE:FF

The _clean_nvm autouse fixture sends PERSIST CLEAR before each test so every
test starts from a known invalid-NVM state.
"""

import asyncio
import re

import pytest

from conftest import BleSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _clear(s: BleSession) -> None:
    resp = await s.send("PERSIST CLEAR")
    assert resp == "OK CLEARED"


async def _read(s: BleSession) -> dict[str, str]:
    """Send PERSIST READ and return the fields as a dict."""
    resp = await s.send("PERSIST READ")
    assert resp.startswith("PERSIST "), f"unexpected response: {resp!r}"
    fields: dict[str, str] = {}
    for token in resp.split()[1:]:   # skip leading "PERSIST" word
        if "=" in token:
            k, _, v = token.partition("=")
            fields[k] = v
    return fields


_CAL_RE = re.compile(r"^[+-]\d+\.\d+,[+-]\d+\.\d+,[+-]\d+\.\d+$")
_LST_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_RTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# ---------------------------------------------------------------------------
# Autouse setup: clear NVM before every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _clean_nvm(device_addr):
    async with BleSession(device_addr) as s:
        await _clear(s)
    yield


# ---------------------------------------------------------------------------
# PERSIST READ — response format
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_read_format(device_addr):
    """PERSIST READ returns all expected fields with correct value types."""
    async with BleSession(device_addr) as s:
        fields = await _read(s)
    assert "valid" in fields
    assert fields["valid"] in ("0", "1")
    assert "tz" in fields
    assert "cal" in fields
    assert "sid" in fields
    assert fields["sid"] in ("on", "off")
    assert "lst" in fields
    assert "rtc" in fields


@pytest.mark.asyncio
async def test_persist_read_after_clear_is_invalid(device_addr):
    """PERSIST READ immediately after CLEAR reports valid=0."""
    async with BleSession(device_addr) as s:
        fields = await _read(s)   # _clean_nvm already ran CLEAR
    assert fields["valid"] == "0"


# ---------------------------------------------------------------------------
# PERSIST CLEAR
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_clear_response(device_addr):
    """PERSIST CLEAR returns OK CLEARED."""
    async with BleSession(device_addr) as s:
        resp = await s.send("PERSIST CLEAR")
    assert resp == "OK CLEARED"


# ---------------------------------------------------------------------------
# PERSIST — save state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_saves_timezone(device_addr):
    """PERSIST records the timezone label; PERSIST READ echoes it back."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z UTC")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        assert "tz=UTC" in resp
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["tz"] == "UTC"


@pytest.mark.asyncio
async def test_persist_saves_calibration(device_addr):
    """PERSIST records the calibration ref vector; values match CALIBRATE output."""
    async with BleSession(device_addr) as s:
        cal_resp = await s.send("CALIBRATE")
        assert cal_resp.startswith("CALIBRATED "), f"unexpected: {cal_resp!r}"
        _, gx, gy, gz = cal_resp.split()
        resp = await s.send("PERSIST")
        assert "cal=" in resp
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert _CAL_RE.match(fields["cal"]), f"unexpected cal format: {fields['cal']!r}"
    stored = fields["cal"].split(",")
    assert abs(float(stored[0]) - float(gx)) < 1e-3
    assert abs(float(stored[1]) - float(gy)) < 1e-3
    assert abs(float(stored[2]) - float(gz)) < 1e-3


@pytest.mark.asyncio
async def test_persist_sidereal_mode(device_addr):
    """PERSIST in sidereal mode stores sid=on with a valid lst and rtc anchor."""
    async with BleSession(device_addr) as s:
        # Need a valid RTC epoch for the anchor
        await s.send("SET_TIME 2025-05-18T12:00:00Z UTC")
        await s.send("SET_SIDEREAL_TIME 05:30:00 LST")
        resp = await s.send("PERSIST")
        assert "sid=on" in resp
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["sid"] == "on"
    assert _LST_RE.match(fields["lst"]), f"unexpected lst format: {fields['lst']!r}"
    assert _RTC_RE.match(fields["rtc"]), f"unexpected rtc format: {fields['rtc']!r}"


@pytest.mark.asyncio
async def test_persist_solar_mode_stores_sid_off(device_addr):
    """PERSIST in solar mode stores sid=off and no lst/rtc anchor."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z UTC")
        resp = await s.send("PERSIST")
        assert "sid=off" in resp
        fields = await _read(s)
    assert fields["sid"] == "off"
    assert fields["lst"] == "(none)"
    assert fields["rtc"] == "(none)"


# ---------------------------------------------------------------------------
# PERSIST RESTORE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_restore_after_clear(device_addr):
    """PERSIST RESTORE re-enables cleared data and applies it to RAM in-session."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00 CET")
        await s.send("PERSIST")
        # Clear so valid=0
        await _clear(s)
        assert (await _read(s))["valid"] == "0"
        # Restore — one NVM write, then re-applies data
        resp = await s.send("PERSIST RESTORE")
        assert resp.startswith("OK RESTORED"), f"unexpected: {resp!r}"
        assert "tz=CET" in resp
        # NVM should be valid again
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["tz"] == "CET"


@pytest.mark.asyncio
async def test_persist_restore_is_idempotent(device_addr):
    """PERSIST RESTORE when NVM is already valid=1 succeeds and echoes stored values."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z UTC")
        await s.send("PERSIST")
        # Restore when already valid
        resp = await s.send("PERSIST RESTORE")
    assert resp.startswith("OK RESTORED"), f"unexpected: {resp!r}"
    assert "tz=UTC" in resp


# ---------------------------------------------------------------------------
# REBOOT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reboot_returns_ok(device_addr):
    """REBOOT returns OK REBOOTING before the connection drops."""
    async with BleSession(device_addr) as s:
        resp = await s.send("REBOOT", timeout=5.0)
    assert resp == "OK REBOOTING"
    # Give the device time to boot before subsequent tests connect
    await asyncio.sleep(4.0)


# ---------------------------------------------------------------------------
# Persistence across reboot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_survives_reboot(device_addr):
    """Settings saved with PERSIST are restored automatically after REBOOT."""
    # Phase 1 — set state, persist, reboot
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00 JST")
        cal_resp = await s.send("CALIBRATE")
        _, gx, gy, gz = cal_resp.split()
        await s.send("PERSIST")
        await s.send("REBOOT", timeout=5.0)

    await asyncio.sleep(5.0)

    # Phase 2 — reconnect and verify NVM was applied on boot
    async with BleSession(device_addr) as s:
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["tz"] == "JST"
    stored = fields["cal"].split(",")
    assert abs(float(stored[0]) - float(gx)) < 1e-3
    assert abs(float(stored[1]) - float(gy)) < 1e-3
    assert abs(float(stored[2]) - float(gz)) < 1e-3


@pytest.mark.asyncio
async def test_clear_survives_reboot(device_addr):
    """PERSIST CLEAR survives a REBOOT — the device boots with NVM still invalid."""
    # Phase 1 — save something, clear it, reboot
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z UTC")
        await s.send("PERSIST")
        await _clear(s)
        await s.send("REBOOT", timeout=5.0)

    await asyncio.sleep(5.0)

    # Phase 2 — verify NVM is still invalid after boot
    async with BleSession(device_addr) as s:
        fields = await _read(s)
    assert fields["valid"] == "0"

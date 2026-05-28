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


_CAL_RE      = re.compile(r"^[+-]\d+\.\d+,[+-]\d+\.\d+,[+-]\d+\.\d+$")
_LON_RE      = re.compile(r"^-?\d+\.\d+$")
_VALID_AXES  = {"+X", "-X", "+Y", "-Y"}
_AXIS_PAIR_RE = re.compile(r"^([+\-][XY]),([+\-][XY])$")


# ---------------------------------------------------------------------------
# Autouse setup: clear NVM before every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _clean_nvm(device_addr):
    async with BleSession(device_addr) as s:
        await _clear(s)
        # Reset in-RAM state that tests might change
        await s.send("SET_LONGITUDE NONE")
        await s.send("SET_PITCHROLL +X,+Y")
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
    assert "tz_offset" in fields
    # tz_offset is an integer (possibly negative)
    int(fields["tz_offset"])
    assert "lon" in fields
    # lon is either a float string or "(none)"
    assert fields["lon"] == "(none)" or _LON_RE.match(fields["lon"])
    assert "cal" in fields
    assert "pitchroll" in fields
    m = _AXIS_PAIR_RE.match(fields["pitchroll"])
    assert m, f"unexpected pitchroll format: {fields['pitchroll']!r}"
    assert m.group(1) in _VALID_AXES
    assert m.group(2) in _VALID_AXES


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
    assert fields["tz_offset"] == "0"


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
async def test_persist_sidereal_mode_via_timezone(device_addr):
    """PERSIST in sidereal mode stores tz=LST and a longitude value."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z")
        await s.send("SET_LONGITUDE 135.0")
        await s.send("SET_TIME_ZONE LST")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        assert "tz=LST" in resp
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["tz"] == "LST"
    assert fields["lon"] != "(none)"
    assert _LON_RE.match(fields["lon"]), f"unexpected lon format: {fields['lon']!r}"


@pytest.mark.asyncio
async def test_persist_solar_mode(device_addr):
    """PERSIST in solar mode stores tz_offset and lon=(none) when no longitude is set."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T12:00:00Z")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        fields = await _read(s)
    assert fields["tz"] == "UTC"
    assert fields["tz_offset"] == "0"
    assert fields["lon"] == "(none)"


@pytest.mark.asyncio
async def test_persist_saves_timezone_offset(device_addr):
    """PERSIST records the numeric UTC offset when SET_TIME carried a +HH:MM suffix."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2025-05-18T21:00:00+09:00")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["tz_offset"] == "32400"


@pytest.mark.asyncio
async def test_persist_saves_longitude(device_addr):
    """PERSIST records the longitude when SET_LONGITUDE was used."""
    async with BleSession(device_addr) as s:
        await s.send("SET_LONGITUDE -3.7")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert _LON_RE.match(fields["lon"]), f"unexpected lon format: {fields['lon']!r}"
    assert abs(float(fields["lon"]) - (-3.7)) < 0.01


@pytest.mark.asyncio
async def test_persist_saves_pitchroll(device_addr):
    """PERSIST records the pitch/roll axis assignment set via SET_PITCHROLL."""
    async with BleSession(device_addr) as s:
        await s.send("SET_PITCHROLL -X,+Y")
        resp = await s.send("PERSIST")
        assert resp.startswith("OK PERSISTED"), f"unexpected: {resp!r}"
        assert "pitchroll=-X,+Y" in resp
        fields = await _read(s)
    assert fields["valid"] == "1"
    assert fields["pitchroll"] == "-X,+Y"


@pytest.mark.asyncio
async def test_persist_pitchroll_default_is_plus_x_plus_y(device_addr):
    """Default pitchroll after PERSIST CLEAR is +X,+Y (applied by Nvm::load)."""
    async with BleSession(device_addr) as s:
        # _clean_nvm fixture already cleared NVM and set pitchroll to +X,+Y.
        # Verify that GET_PITCHROLL reflects the default.
        resp = await s.send("GET_PITCHROLL")
    assert resp == "PITCHROLL +X,+Y"


@pytest.mark.asyncio
async def test_persist_pitchroll_survives_restore(device_addr):
    """PERSIST RESTORE re-applies a saved pitchroll assignment in-session."""
    async with BleSession(device_addr) as s:
        await s.send("SET_PITCHROLL +X,-Y")
        await s.send("PERSIST")
        await _clear(s)
        assert (await _read(s))["valid"] == "0"
        # Restore — pitchroll should come back
        resp = await s.send("PERSIST RESTORE")
        assert resp.startswith("OK RESTORED"), f"unexpected: {resp!r}"
        assert "pitchroll=+X,-Y" in resp
        resp = await s.send("GET_PITCHROLL")
    assert resp == "PITCHROLL +X,-Y"


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
        await s.send_no_wait("REBOOT")  # connection drops; don't wait for notification

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
        await s.send_no_wait("REBOOT")  # connection drops; don't wait for notification

    await asyncio.sleep(5.0)

    # Phase 2 — verify NVM is still invalid after boot
    async with BleSession(device_addr) as s:
        fields = await _read(s)
    assert fields["valid"] == "0"

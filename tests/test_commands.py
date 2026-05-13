"""Tests for the documented BLE command interface.

Each test opens a fresh BLE connection so device state from one test
cannot bleed into another.  Run with::

    pytest test/ --device F0:24:F9:9B:E2:52
"""

import re
import pytest
from conftest import BleSession


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping(device_addr):
    async with BleSession(device_addr) as s:
        assert await s.send("PING") == "OK PONG"


@pytest.mark.asyncio
async def test_ping_case_insensitive(device_addr):
    async with BleSession(device_addr) as s:
        assert await s.send("ping") == "OK PONG"


@pytest.mark.asyncio
async def test_get_tilt_format(device_addr):
    """GET_TILT should return TILT <±X.XX> <±Y.XX>."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_TILT")
    assert resp.startswith("TILT ")
    parts = resp.split()
    assert len(parts) == 3
    # Both values must be parseable as floats
    float(parts[1])
    float(parts[2])


@pytest.mark.asyncio
async def test_get_status_fields(device_addr):
    """GET_STATUS should include SCREEN, BLE, STREAM, BAT, NIGHT key=value pairs."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_STATUS")
    assert resp.startswith("STATUS ")
    assert "SCREEN=" in resp
    assert "BLE=" in resp
    assert "STREAM=" in resp
    assert "BAT=" in resp
    assert "NIGHT=" in resp


@pytest.mark.asyncio
async def test_get_time_format(device_addr):
    """GET_TIME should return TIME <ISO-8601> or TIME NONE."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_TIME")
    assert resp.startswith("TIME ")
    payload = resp[5:]
    if payload != "NONE":
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload), (
            f"Expected ISO-8601 timestamp, got: {payload!r}"
        )


@pytest.mark.asyncio
async def test_get_radec_format(device_addr):
    """GET_RADEC should return two space-separated tokens."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_RADEC")
    assert resp.startswith("RADEC ")
    assert len(resp.split()) == 3


@pytest.mark.asyncio
async def test_get_altaz_format(device_addr):
    """GET_ALTAZ should return two space-separated tokens."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_ALTAZ")
    assert resp.startswith("ALTAZ ")
    assert len(resp.split()) == 3


@pytest.mark.asyncio
async def test_get_msg_none_when_no_message(device_addr):
    """GET_MSG returns MSG NONE when no message is active."""
    async with BleSession(device_addr) as s:
        await s.send("CANCEL_MSG")  # clear any leftover state
        resp = await s.send("GET_MSG")
    assert resp == "MSG NONE"


# ---------------------------------------------------------------------------
# SET_TIME
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_time_valid(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME 2026-01-15T12:00:00Z")
    assert resp == "OK TIME"


@pytest.mark.asyncio
async def test_set_time_roundtrip(device_addr):
    """Set time, then read it back; date and hour should match."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2026-06-20T08:30:00Z")
        resp = await s.send("GET_TIME")
    assert resp.startswith("TIME 2026-06-20T08:"), resp


@pytest.mark.asyncio
async def test_set_time_bad_format(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME not-a-date")
    assert resp == "ERR BAD_TIME"


@pytest.mark.asyncio
async def test_set_time_missing_arg(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME")
    assert resp == "ERR BAD_ARGS"


# ---------------------------------------------------------------------------
# SET_RADEC / GET_RADEC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_radec_valid(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_RADEC 12:34:56 +07:08:09")
    assert resp == "OK RADEC"


@pytest.mark.asyncio
async def test_set_radec_roundtrip(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("SET_RADEC 05:30:00 -05:20:00")
        resp = await s.send("GET_RADEC")
    assert "05:30:00" in resp
    assert "-05:20:00" in resp


@pytest.mark.asyncio
async def test_set_radec_missing_args(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_RADEC 12:34:56")
    assert resp == "ERR BAD_ARGS"


# ---------------------------------------------------------------------------
# SET_ALTAZ / GET_ALTAZ
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_altaz_valid(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_ALTAZ +43.20 180.50")
    assert resp == "OK ALTAZ"


@pytest.mark.asyncio
async def test_set_altaz_roundtrip(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("SET_ALTAZ +33.50 270.00")
        resp = await s.send("GET_ALTAZ")
    assert "+33.50" in resp
    assert "270.00" in resp


@pytest.mark.asyncio
async def test_set_altaz_missing_args(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_ALTAZ +43.20")
    assert resp == "ERR BAD_ARGS"


# ---------------------------------------------------------------------------
# SHOW_MSG / CANCEL_MSG / GET_MSG
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_show_msg_timed(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 Hello world")
        assert resp == "OK MSG"
        resp = await s.send("GET_MSG")
        assert "ACTIVE" in resp
        assert "Hello world" in resp
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_persistent(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG INF Permanent message")
        assert resp == "OK MSG"
        resp = await s.send("GET_MSG")
        assert "ACTIVE" in resp
        assert "INF" in resp
        assert "Permanent message" in resp
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_missing_args(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 5")
    assert resp == "ERR BAD_ARGS"


@pytest.mark.asyncio
async def test_show_msg_wait(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT 30 M5 Press M5 to confirm")
        assert resp == "OK MSG_WAIT"
        resp = await s.send("GET_MSG")
        assert "ACTIVE" in resp
        assert "BUTTONS=M5" in resp
        assert "Press M5 to confirm" in resp
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_multi_buttons(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT 30 M5,A Choose a button")
        assert resp == "OK MSG_WAIT"
        resp = await s.send("GET_MSG")
        assert "M5" in resp and "A" in resp
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_any(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT 30 ANY Any button works")
        assert resp == "OK MSG_WAIT"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_cancel_msg(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("SHOW_MSG 60 Temporary")
        resp = await s.send("CANCEL_MSG")
        assert resp == "OK MSG_CANCEL"
        resp = await s.send("GET_MSG")
        assert resp == "MSG NONE"


# ---------------------------------------------------------------------------
# START_STREAM / STOP_STREAM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_stream(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("START_STREAM 500")
        assert resp == "OK STREAM 500"
        await s.send_no_wait("STOP_STREAM")


@pytest.mark.asyncio
async def test_stream_minimum_period(device_addr):
    """Periods below 100ms are clamped to 100."""
    async with BleSession(device_addr) as s:
        resp = await s.send("START_STREAM 50")
        assert resp == "OK STREAM 100"
        await s.send_no_wait("STOP_STREAM")


@pytest.mark.asyncio
async def test_stop_stream(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("START_STREAM 200")
        resp = await s.send("STOP_STREAM")
        assert resp == "OK STREAM 0"


@pytest.mark.asyncio
async def test_stream_packets(device_addr):
    """Stream should deliver TILT packets at the requested interval."""
    async with BleSession(device_addr) as s:
        await s.send("START_STREAM 200")
        for _ in range(3):
            pkt = await s.recv(timeout=1.0)
            assert pkt.startswith("TILT ")
            parts = pkt.split()
            assert len(parts) == 3
            float(parts[1])
            float(parts[2])
        await s.send_no_wait("STOP_STREAM")
        # Drain the queue until we see the OK (skipping any in-flight TILT packets)
        await s.recv_matching("OK STREAM", timeout=2.0)


@pytest.mark.asyncio
async def test_start_stream_missing_arg(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("START_STREAM")
    assert resp == "ERR BAD_ARGS"


# ---------------------------------------------------------------------------
# SET_NIGHT_MODE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_night_mode_on(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_NIGHT_MODE ON")
        assert resp == "OK NIGHT_MODE ON"
        await s.send("SET_NIGHT_MODE OFF")


@pytest.mark.asyncio
async def test_night_mode_off(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("SET_NIGHT_MODE ON")
        resp = await s.send("SET_NIGHT_MODE OFF")
        assert resp == "OK NIGHT_MODE OFF"


@pytest.mark.asyncio
async def test_night_mode_reflected_in_status(device_addr):
    async with BleSession(device_addr) as s:
        await s.send("SET_NIGHT_MODE ON")
        status = await s.send("GET_STATUS")
        assert "NIGHT=1" in status
        await s.send("SET_NIGHT_MODE OFF")
        status = await s.send("GET_STATUS")
        assert "NIGHT=0" in status


@pytest.mark.asyncio
async def test_night_mode_bad_arg(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_NIGHT_MODE MAYBE")
    assert resp == "ERR BAD_ARGS"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_command(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("FROBNICATE")
    assert resp == "ERR UNKNOWN_COMMAND"


@pytest.mark.asyncio
async def test_empty_command(device_addr):
    """Sending only whitespace/newlines should return ERR BAD_ARGS."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"   ")
    assert raw.startswith(b"ERR")

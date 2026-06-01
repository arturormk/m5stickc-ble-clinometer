"""Tests for the dynamic newline-termination protocol.

When a client sends commands ending with \\n, the device detects this and
appends \\n to every subsequent reply and notification for that connection.
Clients that send commands without \\n receive plain (no-\\n) responses.

The flag is sticky within a connection and resets on disconnect.
"""

import pytest
from conftest import BleSession


# ---------------------------------------------------------------------------
# Detection and basic framing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_newline_command_yields_no_newline_response(device_addr):
    """Command without \\n → response bytes must not end with \\n."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING")
    assert not raw.endswith(b"\n"), (
        f"Expected no trailing \\n, got {raw!r}"
    )
    assert raw == b"OK PONG"


@pytest.mark.asyncio
async def test_newline_command_yields_newline_response(device_addr):
    """Command ending with \\n → response bytes must end with \\n."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING\n")
    assert raw.endswith(b"\n"), (
        f"Expected trailing \\n, got {raw!r}"
    )
    assert raw.rstrip(b"\r\n") == b"OK PONG"


@pytest.mark.asyncio
async def test_crlf_command_yields_newline_response(device_addr):
    """Command ending with \\r\\n (Windows line ending) should also activate the flag."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING\r\n")
    assert raw.endswith(b"\n"), (
        f"Expected trailing \\n for \\r\\n-terminated command, got {raw!r}"
    )


# ---------------------------------------------------------------------------
# Sticky flag — stays set for the lifetime of the connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_newline_flag_is_sticky_within_connection(device_addr):
    """Once the flag is set by one \\n command, all subsequent replies get \\n too."""
    async with BleSession(device_addr) as s:
        # Activate newline mode
        raw1 = await s.send_raw(b"PING\n")
        assert raw1.endswith(b"\n"), "first command should activate the flag"

        # Second command sent WITHOUT \\n — flag should still be set
        raw2 = await s.send_raw(b"PING")
        assert raw2.endswith(b"\n"), (
            "flag should remain set after initial detection; "
            f"got {raw2!r}"
        )

        # Multiple subsequent commands should all carry \\n
        for cmd in (b"GET_TILT", b"GET_STATUS"):
            raw = await s.send_raw(cmd)
            assert raw.endswith(b"\n"), f"expected \\n on {cmd!r} response, got {raw!r}"


# ---------------------------------------------------------------------------
# Flag resets on reconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.ble_reconnect
async def test_newline_flag_resets_on_reconnect(device_addr):
    """A new connection should start without the newline flag set."""
    # First connection: activate newline mode
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING\n")
        assert raw.endswith(b"\n")

    # Second connection: flag must be cleared
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING")
        assert not raw.endswith(b"\n"), (
            f"flag should have reset after reconnect, got {raw!r}"
        )


# ---------------------------------------------------------------------------
# Notifications follow the same convention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_newline_stream_notifications_carry_newline(device_addr):
    """TILT stream notifications should end with \\n when newline mode is active."""
    async with BleSession(device_addr) as s:
        # Activate newline mode
        pong = await s.send_raw(b"PING\n")
        assert pong.endswith(b"\n")

        # Start stream.  Use send_no_wait so we control response consumption:
        # OK STREAM and the first TILT notifications may arrive in any order.
        await s.send_no_wait("START_STREAM 200\n")  # \n keeps newline flag active
        pkt = await s.recv_raw(timeout=1.0)
        while not pkt.rstrip(b"\r\n").startswith(b"OK STREAM"):
            pkt = await s.recv_raw(timeout=1.0)

        # Each TILT notification must carry \\n
        for _ in range(3):
            pkt = await s.recv_raw(timeout=1.0)
            assert pkt.endswith(b"\n"), (
                f"stream TILT packet should end with \\n, got {pkt!r}"
            )
            assert pkt.rstrip().startswith(b"TILT")

        # Clean up (disconnect will clear the stream flag via bleConnected check)
        await s.send_no_wait("STOP_STREAM")


@pytest.mark.asyncio
@pytest.mark.ble_reconnect
async def test_no_newline_stream_notifications_have_no_newline(device_addr):
    """TILT stream notifications should NOT end with \\n in plain (no-\\n) mode."""
    async with BleSession(device_addr) as s:
        # Use send_no_wait so we control response consumption: OK STREAM and
        # the first TILT notifications may arrive in any order.
        await s.send_no_wait("START_STREAM 200")  # no \\n → flag not set
        pkt = await s.recv_raw(timeout=1.0)
        while not pkt.startswith(b"OK STREAM"):
            pkt = await s.recv_raw(timeout=1.0)

        for _ in range(3):
            pkt = await s.recv_raw(timeout=1.0)
            assert not pkt.endswith(b"\n"), (
                f"stream packet should have no trailing \\n, got {pkt!r}"
            )
            assert pkt.startswith(b"TILT")

        await s.send_no_wait("STOP_STREAM")

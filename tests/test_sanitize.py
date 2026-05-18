"""Tests for BLE input sanitisation (Change A).

Covers three behaviours added to the command handler in BleManager.cpp:

1. Common Unicode space variants — NBSP (U+00A0) and ideographic space (U+3000) —
   are silently normalised to ASCII 0x20 before tokenisation, so commands pasted
   from an IME or iOS/Android keyboard still parse correctly.

2. ASCII control characters (byte value < 0x20 or == 0x7F) that survive the
   trailing-whitespace strip are rejected with ERR INVALID_CHAR U+XXXX before
   any tokenisation occurs.

3. The trailing \\n / \\r\\n strip that already existed runs *before* sanitisation,
   so newline-terminated clients are not affected by the control-character check.
"""

import pytest
from conftest import BleSession

# NBSP U+00A0 encodes to two bytes: C2 A0
NBSP = " "
# Ideographic space U+3000 encodes to three bytes: E3 80 80
IDEOGRAPHIC_SPACE = "　"


# ---------------------------------------------------------------------------
# Baseline — sanitiser must not affect normal commands
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plain_ascii_unaffected(device_addr):
    """Ordinary printable-ASCII command must work as before."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING") == "OK PONG"


# ---------------------------------------------------------------------------
# NBSP normalisation (U+00A0, encodes as C2 A0 in UTF-8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nbsp_trailing(device_addr):
    """Trailing NBSP is normalised to space then stripped; PING succeeds."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING" + NBSP) == "OK PONG"


@pytest.mark.asyncio
async def test_nbsp_leading(device_addr):
    """Leading NBSP normalises to a space that strtok_r skips as a delimiter."""
    async with BleSession(device_addr) as s:
        assert await s.send(NBSP + "PING") == "OK PONG"


@pytest.mark.asyncio
async def test_nbsp_as_word_separator(device_addr):
    """NBSP between tokens acts as a word separator after normalisation."""
    async with BleSession(device_addr) as s:
        # "SHOW_MSG<NBSP>5<NBSP>Hello" normalises to "SHOW_MSG 5 Hello"
        resp = await s.send("SHOW_MSG" + NBSP + "5" + NBSP + "Hello")
        assert resp == "OK MSG"
        await s.send("CANCEL_MSG")


# ---------------------------------------------------------------------------
# Ideographic space normalisation (U+3000, encodes as E3 80 80 in UTF-8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ideographic_space_trailing(device_addr):
    """Trailing U+3000 is normalised to space then stripped; PING succeeds."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING" + IDEOGRAPHIC_SPACE) == "OK PONG"


@pytest.mark.asyncio
async def test_ideographic_space_leading(device_addr):
    """Leading U+3000 normalises to a space that strtok_r skips."""
    async with BleSession(device_addr) as s:
        assert await s.send(IDEOGRAPHIC_SPACE + "PING") == "OK PONG"


# ---------------------------------------------------------------------------
# Control character rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_control_char_soh_rejected(device_addr):
    """SOH (U+0001) embedded in a write is rejected with ERR INVALID_CHAR U+0001."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING\x01") == "ERR INVALID_CHAR U+0001"


@pytest.mark.asyncio
async def test_control_char_tab_rejected(device_addr):
    """HT (U+0009, tab) embedded in a write is rejected with ERR INVALID_CHAR U+0009."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING\x09") == "ERR INVALID_CHAR U+0009"


@pytest.mark.asyncio
async def test_control_char_esc_rejected(device_addr):
    """ESC (U+001B) embedded in a write is rejected with ERR INVALID_CHAR U+001B."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING\x1b") == "ERR INVALID_CHAR U+001B"


@pytest.mark.asyncio
async def test_control_char_del_rejected(device_addr):
    """DEL (U+007F) is rejected with ERR INVALID_CHAR U+007F."""
    async with BleSession(device_addr) as s:
        assert await s.send("PING\x7f") == "ERR INVALID_CHAR U+007F"


@pytest.mark.asyncio
async def test_control_char_mid_command_rejected(device_addr):
    """Control byte between valid tokens is caught and reported."""
    async with BleSession(device_addr) as s:
        assert await s.send("GET\x02STATUS") == "ERR INVALID_CHAR U+0002"


@pytest.mark.asyncio
async def test_control_char_before_command_rejected(device_addr):
    """Control byte before the command token is caught before tokenisation."""
    async with BleSession(device_addr) as s:
        assert await s.send("\x03PING") == "ERR INVALID_CHAR U+0003"


# ---------------------------------------------------------------------------
# Trailing \n and \r\n — stripped before sanitise, so not rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trailing_lf_not_rejected(device_addr):
    """Trailing \\n is stripped before sanitise runs; command succeeds normally."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING\n")
    assert raw.rstrip(b"\r\n") == b"OK PONG"


@pytest.mark.asyncio
async def test_trailing_crlf_not_rejected(device_addr):
    """Trailing \\r\\n is stripped before sanitise runs; command succeeds normally."""
    async with BleSession(device_addr) as s:
        raw = await s.send_raw(b"PING\r\n")
    assert raw.rstrip(b"\r\n") == b"OK PONG"

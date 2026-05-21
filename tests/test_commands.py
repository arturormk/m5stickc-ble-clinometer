"""Tests for the documented BLE command interface.

Each test opens a fresh BLE connection so device state from one test
cannot bleed into another.  Run with::

    pytest test/ --device F0:24:F9:9B:E2:52
"""

import re
import pytest
from conftest import BleSession


# ---------------------------------------------------------------------------
# HELP
# ---------------------------------------------------------------------------

async def _collect_help(s) -> list[str]:
    """Send HELP and collect lines until the OK sentinel."""
    await s.send_no_wait("HELP")
    lines: list[str] = []
    while True:
        pkt = await s.recv(timeout=5.0)
        if pkt == "OK":
            break
        lines.append(pkt)
    return lines


@pytest.mark.asyncio
async def test_help_returns_command_list(device_addr):
    """HELP returns one packet per command ending with OK; no HELP prefix on any line."""
    async with BleSession(device_addr) as s:
        lines = await _collect_help(s)
    assert "PING" in lines
    assert not any(line.startswith("HELP ") for line in lines)


@pytest.mark.asyncio
async def test_help_synonym(device_addr):
    """? is accepted as a synonym for HELP."""
    async with BleSession(device_addr) as s:
        await s.send_no_wait("?")
        lines: list[str] = []
        while True:
            pkt = await s.recv(timeout=5.0)
            if pkt == "OK":
                break
            lines.append(pkt)
    assert "PING" in lines


@pytest.mark.asyncio
async def test_help_format(device_addr):
    """HELP output starts with a header line and blank separator, ends with a blank line,
    and includes a BEEP melody example after the BEEP synopsis."""
    async with BleSession(device_addr) as s:
        lines = await _collect_help(s)
    assert lines[0] == "Commands: (case-insensitive)"
    assert lines[1] == ""
    assert lines[-1] == ""
    assert "  e.g. BEEP C'4 G8 -16 G8 A4 G4 -2 B4 C'4" in lines


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
    """GET_TILT should return TILT <±pitch> <±roll> <g>."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_TILT")
    assert resp.startswith("TILT ")
    parts = resp.split()
    assert len(parts) == 4
    float(parts[1])   # pitch degrees
    float(parts[2])   # roll degrees
    g = float(parts[3])
    assert 0.5 <= g <= 1.5, f"gravity magnitude {g}g out of expected range for a stationary device"


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
    """GET_TIME should return TIME NONE, ISO-8601 (Z or tz label), or HH:MM:SS <label>."""
    async with BleSession(device_addr) as s:
        resp = await s.send("GET_TIME")
    assert resp.startswith("TIME ")
    payload = resp[5:]
    valid = (
        payload == "NONE"
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2} \S+", payload)
        or re.fullmatch(r"\d{2}:\d{2}:\d{2} \S+", payload)
    )
    assert valid, f"Unexpected GET_TIME payload: {payload!r}"


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


@pytest.mark.asyncio
async def test_set_time_with_numeric_offset(device_addr):
    """Embedded numeric offset (+HH:MM) is accepted."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME 2026-05-14T12:30:00+01:00")
    assert resp == "OK TIME"


@pytest.mark.asyncio
async def test_set_time_with_named_tz(device_addr):
    """Space-separated timezone label is accepted."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME 2026-05-14T12:30:00 CET")
    assert resp == "OK TIME"


@pytest.mark.asyncio
async def test_set_time_no_tz_suffix(device_addr):
    """Bare datetime without Z or offset is accepted."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_TIME 2026-05-14T12:30:00")
    assert resp == "OK TIME"


@pytest.mark.asyncio
async def test_get_time_utc_has_z_suffix(device_addr):
    """GET_TIME after a UTC set returns ISO-8601 with Z suffix."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2026-06-20T08:30:00Z")
        resp = await s.send("GET_TIME")
    assert re.fullmatch(r"TIME \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", resp), resp


@pytest.mark.asyncio
async def test_get_time_named_tz_label(device_addr):
    """GET_TIME after a named-tz set returns the label in place of Z."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2026-05-14T12:30:00 JST")
        resp = await s.send("GET_TIME")
    assert resp.startswith("TIME 2026-05-14T12:30:"), resp
    assert resp.endswith(" JST"), resp


@pytest.mark.asyncio
async def test_get_time_numeric_offset_label(device_addr):
    """GET_TIME after a numeric-offset set returns the offset in place of Z."""
    async with BleSession(device_addr) as s:
        await s.send("SET_TIME 2026-05-14T12:30:00+01:00")
        resp = await s.send("GET_TIME")
    assert resp.startswith("TIME 2026-05-14T12:30:"), resp
    assert resp.endswith(" +01:00"), resp


# ---------------------------------------------------------------------------
# SET_SIDEREAL_TIME
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_sidereal_time_valid(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_SIDEREAL_TIME 14:32:00")
    assert resp == "OK SIDEREAL"


@pytest.mark.asyncio
async def test_set_sidereal_time_bad_format(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("SET_SIDEREAL_TIME not-a-time")
    assert resp == "ERR BAD_TIME"


@pytest.mark.asyncio
async def test_get_time_sidereal_format(device_addr):
    """GET_TIME in sidereal mode returns HH:MM:SS LST, not ISO-8601."""
    async with BleSession(device_addr) as s:
        await s.send("SET_SIDEREAL_TIME 14:32:00")
        resp = await s.send("GET_TIME")
    assert re.fullmatch(r"TIME \d{2}:\d{2}:\d{2} LST", resp), resp


@pytest.mark.asyncio
async def test_get_time_sidereal_custom_label(device_addr):
    """GET_TIME in sidereal mode uses a custom label when provided."""
    async with BleSession(device_addr) as s:
        await s.send("SET_SIDEREAL_TIME 20:00:00 GST")
        resp = await s.send("GET_TIME")
    assert re.fullmatch(r"TIME \d{2}:\d{2}:\d{2} GST", resp), resp


@pytest.mark.asyncio
async def test_get_time_sidereal_midnight(device_addr):
    """Sidereal midnight (00:00:00) returns TIME 00:00:00 LST, not TIME NONE."""
    async with BleSession(device_addr) as s:
        await s.send("SET_SIDEREAL_TIME 00:00:00")
        resp = await s.send("GET_TIME")
    assert resp != "TIME NONE", "midnight sidereal must not be reported as NONE"
    assert re.fullmatch(r"TIME \d{2}:\d{2}:\d{2} LST", resp), resp


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


def _parse_screen(status: str) -> str:
    """Extract the SCREEN=<name> value from a GET_STATUS response."""
    for field in status.split():
        if field.startswith("SCREEN="):
            return field[7:]
    return ""


@pytest.mark.asyncio
async def test_show_msg_while_active_preserves_prev_screen(device_addr):
    """SHOW_MSG arriving while MESSAGE is already shown must not overwrite prevScreenIndex.

    Without the fix the second SHOW_MSG would save SCREEN_MESSAGE into
    prevScreenIndex; CANCEL_MSG would then restore that same value, leaving
    the device stuck on a blank MESSAGE screen indefinitely.
    """
    async with BleSession(device_addr) as s:
        await s.send("CANCEL_MSG")  # ensure a clean, non-MESSAGE starting screen
        initial_screen = _parse_screen(await s.send("GET_STATUS"))
        assert initial_screen and initial_screen != "MESSAGE"

        await s.send("SHOW_MSG INF First message")
        # Second SHOW_MSG arrives while already on the MESSAGE screen
        await s.send("SHOW_MSG INF Second message")
        assert "Second message" in await s.send("GET_MSG")

        # After cancel the device must return to the original screen, not MESSAGE
        await s.send("CANCEL_MSG")
        screen_after = _parse_screen(await s.send("GET_STATUS"))
        assert screen_after == initial_screen, (
            f"Expected screen {initial_screen!r} after cancel, got {screen_after!r}"
        )
        assert await s.send("GET_MSG") == "MSG NONE"


@pytest.mark.asyncio
async def test_show_msg_wait_while_active_preserves_prev_screen(device_addr):
    """SHOW_MSG_WAIT arriving while MESSAGE is already shown must not overwrite prevScreenIndex."""
    async with BleSession(device_addr) as s:
        await s.send("CANCEL_MSG")
        initial_screen = _parse_screen(await s.send("GET_STATUS"))
        assert initial_screen and initial_screen != "MESSAGE"

        await s.send("SHOW_MSG_WAIT INF M5 First prompt")
        # Second SHOW_MSG_WAIT arrives while already on the MESSAGE screen
        await s.send("SHOW_MSG_WAIT INF M5 Second prompt")
        assert "Second prompt" in await s.send("GET_MSG")

        await s.send("CANCEL_MSG")
        screen_after = _parse_screen(await s.send("GET_STATUS"))
        assert screen_after == initial_screen, (
            f"Expected screen {initial_screen!r} after cancel, got {screen_after!r}"
        )
        assert await s.send("GET_MSG") == "MSG NONE"


# ---------------------------------------------------------------------------
# SHOW_MSG / SHOW_MSG_WAIT — FONT and BEEP options
# ---------------------------------------------------------------------------

def _msg_text(resp: str) -> str:
    """Extract the body stored in a GET_MSG response (everything after TEXT=)."""
    _, _, tail = resp.partition("TEXT=")
    return tail


def _msg_font(resp: str) -> int:
    """Extract the FONT=<n> value from a GET_MSG response, or -1 if absent."""
    _, _, tail = resp.partition("FONT=")
    if not tail:
        return -1
    return int(tail.split()[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("font_code", [1, 2, 3, 4, 5, 6])
async def test_show_msg_font_code_accepted(device_addr, font_code):
    """FONT:<n> is consumed; the body in GET_MSG excludes the option token."""
    async with BleSession(device_addr) as s:
        resp = await s.send(f"SHOW_MSG 10 FONT:{font_code} Font test")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Font test"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_font_unknown_code_accepted(device_addr):
    """An unrecognised FONT: code (e.g. FONT:99) falls to the default without error."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 FONT:99 Unknown font code")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Unknown font code"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_font_case_insensitive(device_addr):
    """The FONT: keyword is matched case-insensitively."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 font:3 Lowercase font keyword")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Lowercase font keyword"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_beep_option_accepted(device_addr):
    """BEEP at the front of the text field is consumed; body is stored correctly."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 BEEP Alert now")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Alert now"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_beep_case_insensitive(device_addr):
    """The BEEP keyword is matched case-insensitively."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 beep Lowercase beep keyword")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Lowercase beep keyword"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_font_then_beep(device_addr):
    """FONT:<n> followed by BEEP: both consumed, text body is correct."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 FONT:3 BEEP Warning message")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Warning message"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_beep_then_font(device_addr):
    """BEEP followed by FONT:<n>: options may appear in either order."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 BEEP FONT:5 Reversed order")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Reversed order"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_beep_mid_body_preserved(device_addr):
    """The word BEEP in the body (not at the very start) is kept as plain text."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 Ignore BEEP sound")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Ignore BEEP sound"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_no_options_body_unchanged(device_addr):
    """A command with no FONT or BEEP tokens stores the whole text verbatim."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG 10 Plain message text")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Plain message text"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
@pytest.mark.parametrize("font_code", [1, 2, 3, 4, 5, 6])
async def test_show_msg_wait_font_code_accepted(device_addr, font_code):
    """FONT:<n> in SHOW_MSG_WAIT is consumed; the stored body excludes the token."""
    async with BleSession(device_addr) as s:
        resp = await s.send(f"SHOW_MSG_WAIT 10 M5 FONT:{font_code} Wait font test")
        assert resp == "OK MSG_WAIT"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Wait font test"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_beep_option_accepted(device_addr):
    """BEEP in SHOW_MSG_WAIT is consumed; body is stored correctly."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT 10 M5 BEEP Press to confirm")
        assert resp == "OK MSG_WAIT"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Press to confirm"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_font_and_beep_combined(device_addr):
    """FONT:<n> and BEEP together in SHOW_MSG_WAIT; text body is correct."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT INF ANY FONT:6 BEEP Ready?")
        assert resp == "OK MSG_WAIT"
        get = await s.send("GET_MSG")
        assert _msg_text(get) == "Ready?"
        await s.send("CANCEL_MSG")


# ---------------------------------------------------------------------------
# GET_MSG FONT= field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_msg_includes_font_field(device_addr):
    """GET_MSG response includes a FONT=<n> field."""
    async with BleSession(device_addr) as s:
        await s.send("SHOW_MSG 10 Hello")
        get = await s.send("GET_MSG")
        assert "FONT=" in get, f"FONT= field missing from GET_MSG: {get!r}"
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
@pytest.mark.parametrize("font_code", [1, 3, 4, 5, 6])
async def test_get_msg_font_field_reflects_explicit_code(device_addr, font_code):
    """GET_MSG FONT= matches the code that was explicitly supplied."""
    async with BleSession(device_addr) as s:
        await s.send(f"SHOW_MSG 10 FONT:{font_code} Test")
        get = await s.send("GET_MSG")
        assert _msg_font(get) == font_code, (
            f"Expected FONT={font_code}, got {_msg_font(get)} in {get!r}"
        )
        await s.send("CANCEL_MSG")


# ---------------------------------------------------------------------------
# SHOW_MSG / SHOW_MSG_WAIT — automatic Unicode font upgrade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_show_msg_non_ascii_auto_upgrades_font(device_addr):
    """Non-ASCII text with no FONT: directive auto-selects lgfxJapanGothic_24 (code 6)."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG INF Héllo wörld")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_font(get) == 6, (
            f"Expected auto-upgrade to FONT=6, got {_msg_font(get)}: {get!r}"
        )
        assert "Héllo wörld" in get
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_ascii_keeps_default_font(device_addr):
    """Pure-ASCII text with no FONT: directive keeps the default (code 0 = Font4)."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG INF Hello world")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_font(get) == 0, (
            f"Expected FONT=0 for ASCII text, got {_msg_font(get)}: {get!r}"
        )
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_non_ascii_explicit_font_not_overridden(device_addr):
    """An explicit FONT: directive is honoured even when the text contains non-ASCII."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG INF FONT:3 Héllo")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert _msg_font(get) == 3, (
            f"Expected explicit FONT=3 to be preserved, got {_msg_font(get)}: {get!r}"
        )
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_non_ascii_auto_upgrades_font(device_addr):
    """SHOW_MSG_WAIT with non-ASCII text and no FONT: auto-selects code 6."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT INF M5 ¿Continuar?")
        assert resp == "OK MSG_WAIT"
        get = await s.send("GET_MSG")
        assert _msg_font(get) == 6, (
            f"Expected auto-upgrade to FONT=6, got {_msg_font(get)}: {get!r}"
        )
        assert "¿Continuar?" in get
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_wait_non_ascii_explicit_font_not_overridden(device_addr):
    """An explicit FONT: in SHOW_MSG_WAIT is honoured even with non-ASCII text."""
    async with BleSession(device_addr) as s:
        resp = await s.send("SHOW_MSG_WAIT INF M5 FONT:6 ¡Atención!")
        assert resp == "OK MSG_WAIT"
        get = await s.send("GET_MSG")
        assert _msg_font(get) == 6, (
            f"Expected explicit FONT=6 to be preserved, got {_msg_font(get)}: {get!r}"
        )
        await s.send("CANCEL_MSG")


# ---------------------------------------------------------------------------
# SHOW_MSG — word wrap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_show_msg_japanese_no_spaces_accepted(device_addr):
    """A long Japanese string (no spaces) is accepted and stored verbatim.

    The display wraps at character boundaries rather than clipping; this test
    confirms the BLE layer stores the full string correctly.
    """
    text = "今日も小さな幸せがたくさん見つかりますように"
    async with BleSession(device_addr) as s:
        resp = await s.send(f"SHOW_MSG INF FONT:5 {text}")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert text in get
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_long_ascii_no_spaces_accepted(device_addr):
    """A long ASCII token with no spaces (e.g. a URL) is accepted and stored verbatim.

    The display wraps at character boundaries rather than clipping.
    """
    text = "https://www.example.com/very/long/path"
    async with BleSession(device_addr) as s:
        resp = await s.send(f"SHOW_MSG INF {text}")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert text in get
        await s.send("CANCEL_MSG")


@pytest.mark.asyncio
async def test_show_msg_mixed_ascii_and_japanese_accepted(device_addr):
    """A message mixing a space-separated ASCII word and a Japanese run is accepted and stored verbatim.

    The display wraps the ASCII word at the space and the Japanese run at
    character boundaries across subsequent lines.
    """
    text = "Hello 今日も小さな"
    async with BleSession(device_addr) as s:
        resp = await s.send(f"SHOW_MSG INF FONT:5 {text}")
        assert resp == "OK MSG"
        get = await s.send("GET_MSG")
        assert text in get
        await s.send("CANCEL_MSG")


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
        await s.send_no_wait("STOP_STREAM")
        resp = await s.recv_matching("OK STREAM", timeout=2.0)
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
            assert len(parts) == 4
            float(parts[1])   # pitch degrees
            float(parts[2])   # roll degrees
            g = float(parts[3])
            assert 0.5 <= g <= 1.5, f"gravity magnitude {g}g out of expected range for a stationary device"
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
# BEEP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_beep_no_args(device_addr):
    async with BleSession(device_addr) as s:
        resp = await s.send("BEEP")
    assert resp == "OK BEEP"


@pytest.mark.asyncio
async def test_beep_melody(device_addr):
    """Shave-and-a-haircut melody should be accepted and queued."""
    async with BleSession(device_addr) as s:
        resp = await s.send("BEEP C'4 G8 -16 G8 A4 G8 -2 B4 C'4")
    assert resp == "OK BEEP"


@pytest.mark.asyncio
async def test_beep_bad_note(device_addr):
    """Bad note at the start of the melody is flagged with a leading caret."""
    async with BleSession(device_addr) as s:
        resp = await s.send("BEEP Z4")
    assert resp == "ERR BAD_MELODY ^Z4"


@pytest.mark.asyncio
async def test_beep_bad_note_mid_melody(device_addr):
    """Caret appears at the first bad token; valid prefix tokens are echoed before it."""
    async with BleSession(device_addr) as s:
        resp = await s.send("BEEP C4 Z4")
    assert resp == "ERR BAD_MELODY C4 ^Z4"


# ---------------------------------------------------------------------------
# CALIBRATE / CALIBRATE_RESET
# ---------------------------------------------------------------------------

def _parse_calibrated(resp: str) -> tuple[float, float, float]:
    """Parse 'CALIBRATED gx gy gz' and return the three floats."""
    parts = resp.split()
    assert parts[0] == "CALIBRATED" and len(parts) == 4, (
        f"Unexpected CALIBRATE response: {resp!r}"
    )
    return float(parts[1]), float(parts[2]), float(parts[3])


@pytest.mark.asyncio
async def test_calibrate_response_format(device_addr):
    """CALIBRATE returns CALIBRATED <gx> <gy> <gz> where the vector is unit length."""
    async with BleSession(device_addr) as s:
        await s.send("CALIBRATE_RESET")
        resp = await s.send("CALIBRATE")
    gx, gy, gz = _parse_calibrated(resp)
    mag = (gx**2 + gy**2 + gz**2) ** 0.5
    assert abs(mag - 1.0) < 0.01, f"Reference vector magnitude {mag:.4f} is not ~1"


@pytest.mark.asyncio
async def test_calibrate_tilt_near_zero(device_addr):
    """GET_TILT should report near 0°/0° immediately after CALIBRATE."""
    async with BleSession(device_addr) as s:
        await s.send("CALIBRATE")
        resp = await s.send("GET_TILT")
    parts = resp.split()
    pitch, roll = float(parts[1]), float(parts[2])
    assert abs(pitch) < 2.0, f"Pitch {pitch:.2f}° not near zero after CALIBRATE"
    assert abs(roll)  < 2.0, f"Roll  {roll:.2f}° not near zero after CALIBRATE"


@pytest.mark.asyncio
async def test_calibrate_reset_response(device_addr):
    """CALIBRATE_RESET returns OK CALIBRATION_RESET."""
    async with BleSession(device_addr) as s:
        resp = await s.send("CALIBRATE_RESET")
    assert resp == "OK CALIBRATION_RESET"


@pytest.mark.asyncio
async def test_calibrate_with_identity_vector(device_addr):
    """CALIBRATE 0 0 1 sets the identity calibration and echoes (0, 0, 1)."""
    async with BleSession(device_addr) as s:
        resp = await s.send("CALIBRATE 0 0 1")
    gx, gy, gz = _parse_calibrated(resp)
    assert abs(gx)       < 0.001
    assert abs(gy)       < 0.001
    assert abs(gz - 1.0) < 0.001


@pytest.mark.asyncio
async def test_calibrate_with_args_normalises(device_addr):
    """CALIBRATE accepts an unnormalised vector and returns a unit vector."""
    async with BleSession(device_addr) as s:
        resp = await s.send("CALIBRATE 0 0 3")  # magnitude 3, direction (0,0,1)
    gx, gy, gz = _parse_calibrated(resp)
    mag = (gx**2 + gy**2 + gz**2) ** 0.5
    assert abs(mag - 1.0) < 0.001
    assert abs(gz - 1.0)  < 0.001


@pytest.mark.asyncio
async def test_calibrate_roundtrip(device_addr):
    """Save the calibration vector, reset, restore — the vector is identical."""
    async with BleSession(device_addr) as s:
        first = await s.send("CALIBRATE")
        await s.send("CALIBRATE_RESET")
        gx, gy, gz = _parse_calibrated(first)
        second = await s.send(f"CALIBRATE {gx:+.4f} {gy:+.4f} {gz:+.4f}")
    assert first == second, (
        f"Restored calibration {second!r} differs from original {first!r}"
    )


@pytest.mark.asyncio
async def test_calibrate_reset_clears_offset(device_addr):
    """After CALIBRATE + CALIBRATE_RESET, CALIBRATE 0 0 1 restores (0, 0, 1)."""
    async with BleSession(device_addr) as s:
        await s.send("CALIBRATE")           # set some non-identity calibration
        await s.send("CALIBRATE_RESET")     # clear it
        resp = await s.send("CALIBRATE 0 0 1")
    gx, gy, gz = _parse_calibrated(resp)
    assert abs(gx)       < 0.001
    assert abs(gy)       < 0.001
    assert abs(gz - 1.0) < 0.001


@pytest.mark.asyncio
async def test_calibrate_one_arg_rejected(device_addr):
    """CALIBRATE with one float is rejected as ERR BAD_ARGS."""
    async with BleSession(device_addr) as s:
        resp = await s.send("CALIBRATE 0.5")
    assert resp == "ERR BAD_ARGS"


@pytest.mark.asyncio
async def test_calibrate_two_args_rejected(device_addr):
    """CALIBRATE with two floats is rejected as ERR BAD_ARGS."""
    async with BleSession(device_addr) as s:
        resp = await s.send("CALIBRATE 0.5 0.5")
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

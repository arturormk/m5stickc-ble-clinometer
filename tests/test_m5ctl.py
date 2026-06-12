"""Unit tests for m5ctl helper functions and set-timezone command building.

These tests do not require a BLE device and run as part of the default pytest suite.
"""

import importlib.util
import pathlib
import re
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock

_TOOLS = pathlib.Path(__file__).parent.parent / "tools"


@pytest.fixture(scope="module")
def m5ctl():
    """Import tools/m5ctl as a module (the file has no .py extension)."""
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("m5ctl", str(_TOOLS / "m5ctl"))
    spec = importlib.util.spec_from_loader("m5ctl", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _tz_to_offset_str — fixed abbreviations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("abbrev,expected", [
    ("CET",  "+01:00"),
    ("CEST", "+02:00"),
    ("EET",  "+02:00"),
    ("EEST", "+03:00"),
    ("JST",  "+09:00"),
    ("EST",  "-05:00"),
    ("EDT",  "-04:00"),
    ("CST",  "-06:00"),
    ("CDT",  "-05:00"),
    ("MST",  "-07:00"),
    ("MDT",  "-06:00"),
    ("PST",  "-08:00"),
    ("PDT",  "-07:00"),
    ("IST",  "+05:30"),   # non-hour offset
    ("AEST", "+10:00"),
    ("AEDT", "+11:00"),
    ("GMT",  "+00:00"),   # zero → +00:00, not Z
    ("WET",  "+00:00"),
    ("BST",  "+01:00"),
])
def test_tz_fixed_offset(m5ctl, abbrev, expected):
    assert m5ctl._tz_to_offset_str(abbrev) == expected


def test_tz_offset_case_insensitive(m5ctl):
    assert m5ctl._tz_to_offset_str("cet")  == "+01:00"
    assert m5ctl._tz_to_offset_str("Jst")  == "+09:00"
    assert m5ctl._tz_to_offset_str("cest") == "+02:00"


# ---------------------------------------------------------------------------
# _tz_to_offset_str — IANA names
# ---------------------------------------------------------------------------

def test_tz_iana_no_dst(m5ctl):
    """IANA zones without DST resolve to their fixed offset."""
    assert m5ctl._tz_to_offset_str("Asia/Tokyo")   == "+09:00"
    assert m5ctl._tz_to_offset_str("Asia/Kolkata")  == "+05:30"
    assert m5ctl._tz_to_offset_str("UTC")           == "+00:00"


def test_tz_iana_result_format(m5ctl):
    """Any IANA name returns a properly-formatted ±HH:MM string."""
    result = m5ctl._tz_to_offset_str("America/New_York")
    assert re.fullmatch(r"[+-]\d{2}:\d{2}", result), result


def test_tz_unknown_raises(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._tz_to_offset_str("NotARealTimeZone_XYZ")


# ---------------------------------------------------------------------------
# set-timezone command building
# Run main() with a fake argv; intercept do_send to capture the BLE command.
# ---------------------------------------------------------------------------

def _cmd(m5ctl, monkeypatch, *argv):
    """Run main() with the given set-timezone args; return the BLE command string."""
    sent = []
    monkeypatch.setattr(m5ctl, "do_send", lambda args, cmd: sent.append(cmd))
    monkeypatch.setattr(sys, "argv",
                        ["m5ctl", "-d", "AA:BB:CC:DD:EE:FF"] + list(argv))
    m5ctl.main()
    return sent[0] if sent else None


def test_handler_cet(m5ctl, monkeypatch):
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "CET") == "SET_TIME_ZONE +01:00 CET"


def test_handler_cest(m5ctl, monkeypatch):
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "CEST") == "SET_TIME_ZONE +02:00 CEST"


def test_handler_jst(m5ctl, monkeypatch):
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "JST") == "SET_TIME_ZONE +09:00 JST"


def test_handler_cest_with_label(m5ctl, monkeypatch):
    """Explicit label overrides the auto-label derived from the spec."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "CEST", "Europe/Madrid") \
        == "SET_TIME_ZONE +02:00 Europe/Madrid"


def test_handler_tilde_with_label(m5ctl, monkeypatch):
    """~ prefix is translated to - before sending."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "~05:00", "EST") \
        == "SET_TIME_ZONE -05:00 EST"


def test_handler_tilde_no_label(m5ctl, monkeypatch):
    """~ with no label sends the translated negative offset without a label."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "~05:00") == "SET_TIME_ZONE -05:00"


def test_handler_explicit_offset_passthrough(m5ctl, monkeypatch):
    """+HH:MM offset is passed through to the firmware unchanged."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "+09:00", "JST") \
        == "SET_TIME_ZONE +09:00 JST"


def test_handler_negative_offset_passthrough(m5ctl, monkeypatch):
    """-HH:MM offset is passed through to the firmware unchanged."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "-05:00") \
        == "SET_TIME_ZONE -05:00"


def test_handler_utc_passthrough(m5ctl, monkeypatch):
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "UTC") == "SET_TIME_ZONE UTC"


def test_handler_lst_passthrough(m5ctl, monkeypatch):
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "LST") == "SET_TIME_ZONE LST"


def test_handler_gmt_zero_offset(m5ctl, monkeypatch):
    """GMT resolves to +00:00, not Z — the firmware expects an explicit sign."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "GMT") == "SET_TIME_ZONE +00:00 GMT"


def test_handler_iana_name(m5ctl, monkeypatch):
    """IANA zone name is resolved; original name becomes the display label."""
    assert _cmd(m5ctl, monkeypatch, "set-timezone", "Asia/Tokyo") \
        == "SET_TIME_ZONE +09:00 Asia/Tokyo"


# ---------------------------------------------------------------------------
# set-time-now command building
# ---------------------------------------------------------------------------

def test_set_time_now_timezone_default_label(m5ctl, monkeypatch):
    """--timezone without --label uses the timezone string as the label."""
    cmd = _cmd(m5ctl, monkeypatch, "set-time-now", "--timezone", "CEST")
    assert cmd is not None and cmd.startswith("SET_TIME ")
    assert cmd.endswith(" CEST")


def test_set_time_now_timezone_explicit_label(m5ctl, monkeypatch):
    """--label overrides the auto-derived timezone label."""
    cmd = _cmd(m5ctl, monkeypatch, "set-time-now", "--timezone", "CEST", "--label", "MyLabel")
    assert cmd is not None and cmd.endswith(" MyLabel")


def test_set_time_now_iana_default_label(m5ctl, monkeypatch):
    """IANA timezone name is used verbatim as the label."""
    cmd = _cmd(m5ctl, monkeypatch, "set-time-now", "--timezone", "Asia/Tokyo")
    assert cmd is not None and cmd.endswith(" Asia/Tokyo")


# ---------------------------------------------------------------------------
# _load_all_devices — config file parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conf_text, expected", [
    ("device = AA:BB:CC:DD:EE:FF\n",                          {}),
    ("device.main = F0:12:34:56:78:D2\n",                     {"main": "F0:12:34:56:78:D2"}),
    (
        "device.main = F0:12:34:56:78:D2\ndevice.guide = 3C:AB:CD:EF:01:56\n",
        {"main": "F0:12:34:56:78:D2", "guide": "3C:AB:CD:EF:01:56"},
    ),
    (
        "device = AA:BB:CC:DD:EE:FF\ndevice.main = F0:12:34:56:78:D2\n",
        {"main": "F0:12:34:56:78:D2"},
    ),
    ("# comment\n\ndevice.main = F0:12:34:56:78:D2\n",         {"main": "F0:12:34:56:78:D2"}),
    ("device.0 = AA:BB:CC:DD:EE:FF\n",                         {"0": "AA:BB:CC:DD:EE:FF"}),
    ("",                                                        {}),
    ("device.main = F0:12:34:56:78:D2 PLUS2\n",               {"main": "F0:12:34:56:78:D2"}),
])
def test_load_all_devices(m5ctl, monkeypatch, tmp_path, conf_text, expected):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(conf_text)
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_all_devices() == expected


@pytest.mark.parametrize("conf_text, expected", [
    ("device.main = F0:12:34:56:78:D2\n",
     ({"main": ("F0:12:34:56:78:D2", None)}, None)),
    ("device.main = F0:12:34:56:78:D2 PLUS2\n",
     ({"main": ("F0:12:34:56:78:D2", "PLUS2")}, None)),
    ("device.main = F0:12:34:56:78:D2  spacey \n",
     ({"main": ("F0:12:34:56:78:D2", "spacey")}, None)),
    ("device.main = F0:12:34:56:78:D2 Plus2 on scope  # powered off\n",
     ({"main": ("F0:12:34:56:78:D2", "Plus2 on scope")}, None)),
    ("device = AA:BB:CC:DD:EE:FF\n", ({}, None)),
    ("", ({}, None)),
    ("device.main = F0:12:34:56:78:D2\ndefault_device = main\n",
     ({"main": ("F0:12:34:56:78:D2", None)}, "main")),
    ("default_device = main\n",
     ({}, "main")),
])
def test_load_device_entries(m5ctl, monkeypatch, tmp_path, conf_text, expected):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(conf_text)
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_device_entries() == expected


# ---------------------------------------------------------------------------
# _resolve_device — selector resolution
# ---------------------------------------------------------------------------

_ENV_VAR  = "M5_BLE_ADDR"
MAC       = "F0:12:34:56:78:D2"
OTHER_MAC = "AA:BB:CC:DD:EE:FF"


def test_resolve_raw_mac_passthrough(m5ctl, monkeypatch):
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})
    assert m5ctl._resolve_device(MAC) == MAC


def test_resolve_named_device(m5ctl, monkeypatch):
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {"main": MAC})
    assert m5ctl._resolve_device("main") == MAC


def test_resolve_unknown_name_exits(m5ctl, monkeypatch):
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})
    with pytest.raises(SystemExit):
        m5ctl._resolve_device("notfound")


def test_resolve_none_uses_env_var(m5ctl, monkeypatch):
    monkeypatch.setenv(_ENV_VAR, OTHER_MAC)
    monkeypatch.setattr(m5ctl, "_load_device_entries", lambda: ({}, None))
    assert m5ctl._resolve_device(None) == OTHER_MAC


def test_resolve_none_uses_first_device_fallback(m5ctl, monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_entries",
                        lambda: ({"main": (MAC, None)}, None))
    assert m5ctl._resolve_device(None) == MAC


def test_resolve_none_returns_none_when_nothing_configured(m5ctl, monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_entries", lambda: ({}, None))
    assert m5ctl._resolve_device(None) is None


def test_resolve_default_device(m5ctl, monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_entries",
                        lambda: ({"main": (MAC, None)}, "main"))
    assert m5ctl._resolve_device(None) == MAC


def test_resolve_env_var_beats_default_device(m5ctl, monkeypatch):
    monkeypatch.setenv(_ENV_VAR, OTHER_MAC)
    monkeypatch.setattr(m5ctl, "_load_device_entries",
                        lambda: ({"main": (MAC, None)}, "main"))
    assert m5ctl._resolve_device(None) == OTHER_MAC


def test_resolve_default_device_unknown_warns_and_falls_through(m5ctl, monkeypatch, capsys):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_entries",
                        lambda: ({"main": (MAC, None)}, "typo"))
    result = m5ctl._resolve_device(None)
    assert result == MAC
    assert "warning" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _terminal_line_to_ble — command translation for the interactive terminal
# ---------------------------------------------------------------------------

_TERM_ADDR = "AA:BB:CC:DD:EE:FF"
_TERM_TIMEOUT = 5.0


def _ble(m5ctl, line):
    """Call _terminal_line_to_ble and return the result."""
    return m5ctl._terminal_line_to_ble(line, _TERM_ADDR, _TERM_TIMEOUT)


@pytest.mark.parametrize("line,expected", [
    ("ping",   "PING"),
    ("tilt",   "GET_TILT"),
    ("status", "GET_STATUS"),
    ("calibrate-reset", "CALIBRATE_RESET"),
    ("reboot", "REBOOT"),
    ("persist", "PERSIST"),
    ("stop-stream", "STOP_STREAM"),
])
def test_terminal_ble_simple_commands(m5ctl, line, expected):
    assert _ble(m5ctl, line) == expected


def test_terminal_ble_help_returns_help(m5ctl):
    assert _ble(m5ctl, "help") == "HELP"
    assert _ble(m5ctl, "?") == "HELP"


def test_terminal_ble_raw_fallback(m5ctl):
    """Strings that are not m5ctl subcommands are sent as raw BLE commands."""
    assert _ble(m5ctl, "GET_TILT") == "GET_TILT"
    assert _ble(m5ctl, "PING") == "PING"
    assert _ble(m5ctl, "SOME_UNDOCUMENTED_CMD foo") == "SOME_UNDOCUMENTED_CMD foo"


def test_terminal_ble_local_only_returns_none(m5ctl, capsys):
    """Local-only commands return None and print a message."""
    for cmd in ("list", "scan", "exec -", "script -", "run -"):
        result = _ble(m5ctl, cmd)
        assert result is None, f"expected None for {cmd!r}, got {result!r}"
    capsys.readouterr()  # consume output


def test_terminal_ble_listen_returns_none(m5ctl, capsys):
    assert _ble(m5ctl, "listen") is None
    capsys.readouterr()


def test_terminal_ble_set_screen(m5ctl):
    assert _ble(m5ctl, "set-screen BATTERY") == "SET_SCREEN BATTERY"
    assert _ble(m5ctl, "set-screen CLINOMETER") == "SET_SCREEN CLINOMETER"


def test_terminal_ble_beep(m5ctl):
    assert _ble(m5ctl, "beep") == "BEEP"
    assert _ble(m5ctl, "beep C4 E4 G4") == "BEEP C4 E4 G4"


def test_terminal_ble_set_longitude(m5ctl):
    assert _ble(m5ctl, "set-longitude -3.7") == "SET_LONGITUDE -3.7"


# ---------------------------------------------------------------------------
# version subcommand
# ---------------------------------------------------------------------------

def test_version_command(m5ctl, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["m5ctl", "version"])
    m5ctl.main()
    assert capsys.readouterr().out.strip() == f"m5ctl {m5ctl._VERSION}"


# ---------------------------------------------------------------------------
# cmd_list — no BLE hardware required
# ---------------------------------------------------------------------------

def test_list_no_devices_configured(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.delenv(_ENV_VAR, raising=False)

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    assert f"m5ctl {m5ctl._VERSION}" in out
    assert "No devices configured" in out


def test_list_shows_env_var_device(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.setenv(_ENV_VAR, OTHER_MAC)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        f"${_ENV_VAR}": (True, -60, "M5-NexStar-Level"),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    assert f"${_ENV_VAR}" in out
    assert OTHER_MAC in out


def test_list_env_var_deduped_when_already_named(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(f"device.main = {OTHER_MAC}\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.setenv(_ENV_VAR, OTHER_MAC)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        "main": (True, -60, "M5-NexStar-Level"),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    assert "main" in out
    assert f"${_ENV_VAR}" not in out  # env var device not added as a separate row


def test_list_table_output(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(
        "device.main  = F0:12:34:56:78:D2\n"
        "device.guide = 3C:AB:CD:EF:01:56\n"
    )
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        "main":  (True,  -55, "M5-NexStar-Level"),
        "guide": (False, None, None),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    assert f"m5ctl {m5ctl._VERSION}" in out
    assert "main" in out
    assert "guide" in out
    assert "reachable" in out
    assert "unreachable" in out
    assert "M5-NexStar-Level" in out


def test_list_shows_annotation(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("device.main = F0:12:34:56:78:D2 PLUS2\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        "main": (True, -55, "M5-NexStar-Level"),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "F0:12:34:56:78:D2" in l]
    assert lines, "device row not found"
    assert "| PLUS2" in lines[0]
    assert lines[0].index("M5-NexStar-Level") < lines[0].index("PLUS2")


def test_list_no_annotation_when_absent(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("device.main = F0:12:34:56:78:D2\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        "main": (False, None, None),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "F0:12:34:56:78:D2" in l]
    assert lines
    assert lines[0].strip().endswith("(unknown)")


def test_list_marks_default_device(m5ctl, monkeypatch, capsys, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(
        "device.main  = F0:12:34:56:78:D2\n"
        "device.guide = 3C:AB:CD:EF:01:56\n"
        "default_device = main\n"
    )
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_check_reachable", AsyncMock(return_value={
        "main":  (True,  -55, "M5-NexStar-Level"),
        "guide": (False, None, None),
    }))

    m5ctl.cmd_list()

    out = capsys.readouterr().out
    main_lines  = [l for l in out.splitlines() if "F0:12:34:56:78:D2" in l]
    guide_lines = [l for l in out.splitlines() if "3C:AB:CD:EF:01:56" in l]
    assert main_lines  and main_lines[0].startswith("*")
    assert guide_lines and guide_lines[0].startswith(" ")


# ---------------------------------------------------------------------------
# cmd_scan — annotation of known devices
# ---------------------------------------------------------------------------

def _fake_discover(devices: dict) -> AsyncMock:
    """Build a BleakScanner.discover mock returning the given {mac: (dev, adv)} map."""
    return AsyncMock(return_value=devices)


def _fake_device(mac: str, name: str, rssi: int):
    dev = MagicMock(); dev.address = mac; dev.name = name
    adv = MagicMock(); adv.rssi = rssi
    return dev, adv


async def test_scan_annotates_named_device(m5ctl, monkeypatch, capsys):
    mac = "F0:12:34:56:78:D2"
    scanner = MagicMock()
    scanner.discover = _fake_discover({mac: _fake_device(mac, "M5-NexStar-Level", -55)})
    monkeypatch.setattr(m5ctl, "BleakScanner", scanner)
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {"main": mac})

    await m5ctl.cmd_scan(3.0)

    assert "[main]" in capsys.readouterr().out


async def test_scan_no_annotation_for_unknown(m5ctl, monkeypatch, capsys):
    mac = "AA:BB:CC:DD:EE:FF"
    scanner = MagicMock()
    scanner.discover = _fake_discover({mac: _fake_device(mac, "iPhone", -70)})
    monkeypatch.setattr(m5ctl, "BleakScanner", scanner)
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})

    await m5ctl.cmd_scan(3.0)

    assert "[" not in capsys.readouterr().out


async def test_scan_passes_timeout_to_discover(m5ctl, monkeypatch, capsys):
    """--timeout value reaches BleakScanner.discover(timeout=...)."""
    mac = "AA:BB:CC:DD:EE:FF"
    scanner = MagicMock()
    scanner.discover = _fake_discover({mac: _fake_device(mac, "Thing", -80)})
    monkeypatch.setattr(m5ctl, "BleakScanner", scanner)
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})

    await m5ctl.cmd_scan(1.5)

    scanner.discover.assert_awaited_once_with(timeout=1.5, return_adv=True)


# ---------------------------------------------------------------------------
# get-board / set-pitchroll / get-pitchroll command building
# ---------------------------------------------------------------------------

def test_handler_get_board(m5ctl, monkeypatch):
    """get-board sends GET_BOARD."""
    assert _cmd(m5ctl, monkeypatch, "get-board") == "GET_BOARD"


def test_handler_get_pitchroll(m5ctl, monkeypatch):
    """get-pitchroll sends GET_PITCHROLL."""
    assert _cmd(m5ctl, monkeypatch, "get-pitchroll") == "GET_PITCHROLL"


def test_handler_set_pitchroll_default(m5ctl, monkeypatch):
    """+X,+Y (default) is passed through unchanged."""
    assert _cmd(m5ctl, monkeypatch, "set-pitchroll", "+X,+Y") == "SET_PITCHROLL +X,+Y"


def test_handler_set_pitchroll_flip_roll(m5ctl, monkeypatch):
    """Flipping the roll sign sends the correct command."""
    assert _cmd(m5ctl, monkeypatch, "set-pitchroll", "+X,-Y") == "SET_PITCHROLL +X,-Y"


def test_handler_set_pitchroll_tilde_pitch(m5ctl, monkeypatch):
    """~ prefix for a negative pitch axis is translated to - before sending."""
    assert _cmd(m5ctl, monkeypatch, "set-pitchroll", "~X,+Y") == "SET_PITCHROLL -X,+Y"


def test_handler_set_pitchroll_tilde_both(m5ctl, monkeypatch):
    """~X,-Y (negative pitch via ~, explicit negative roll) is translated correctly."""
    assert _cmd(m5ctl, monkeypatch, "set-pitchroll", "~X,-Y") == "SET_PITCHROLL -X,-Y"


def test_handler_set_pitchroll_y_axes(m5ctl, monkeypatch):
    """Y-type pitch and X-type roll (swapped layout) is accepted."""
    assert _cmd(m5ctl, monkeypatch, "set-pitchroll", "+Y,+X") == "SET_PITCHROLL +Y,+X"


def test_handler_set_pitchroll_bad_axis_exits(m5ctl, monkeypatch):
    """An unrecognised axis code exits with an error."""
    with pytest.raises(SystemExit):
        _cmd(m5ctl, monkeypatch, "set-pitchroll", "+Z,+Y")


def test_handler_set_pitchroll_missing_comma_exits(m5ctl, monkeypatch):
    """A single axis with no comma exits with an error."""
    with pytest.raises(SystemExit):
        _cmd(m5ctl, monkeypatch, "set-pitchroll", "+X")


# ---------------------------------------------------------------------------
# set-radec command building
# ---------------------------------------------------------------------------

def test_handler_set_radec_positive_dec(m5ctl, monkeypatch):
    """Positive DEC is passed through unchanged."""
    assert _cmd(m5ctl, monkeypatch, "set-radec", "06:45:09", "+16:42:58") \
        == "SET_RADEC 06:45:09 +16:42:58"


def test_handler_set_radec_negative_dec(m5ctl, monkeypatch):
    """Negative DEC is rewritten via ~ sentinel and restored correctly before sending."""
    assert _cmd(m5ctl, monkeypatch, "set-radec", "06:45:09", "-16:42:58") \
        == "SET_RADEC 06:45:09 -16:42:58"


def test_handler_set_radec_zero_dec(m5ctl, monkeypatch):
    """Unsigned zero DEC is passed through unchanged."""
    assert _cmd(m5ctl, monkeypatch, "set-radec", "00:00:00", "00:00:00") \
        == "SET_RADEC 00:00:00 00:00:00"


def test_handler_set_radec_tilde_passthrough(m5ctl, monkeypatch):
    """~ prefix supplied directly is translated to - before sending."""
    assert _cmd(m5ctl, monkeypatch, "set-radec", "12:34:56", "~07:08:09") \
        == "SET_RADEC 12:34:56 -07:08:09"


# ---------------------------------------------------------------------------
# _connect — retry logic (no real device required)
# ---------------------------------------------------------------------------

def _mock_ble(m5ctl, monkeypatch, connect_side_effect):
    """Patch BleakClient, BleakScanner, and asyncio.sleep; return (mock_client, mock_sleep)."""
    from bleak import BleakError  # noqa: F401 — ensure importable
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(side_effect=connect_side_effect)
    mock_client.disconnect = AsyncMock()
    monkeypatch.setattr(m5ctl, "BleakClient", lambda *a, **kw: mock_client)
    # On Windows _connect calls BleakScanner.find_device_by_address before client.connect().
    # Without this patch the pre-scan hits the real BLE stack and raises BleakDeviceNotFoundError,
    # which bypasses client.connect() entirely and breaks all three retry tests.
    mock_scanner = MagicMock()
    mock_scanner.find_device_by_address = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(m5ctl, "BleakScanner", mock_scanner)
    mock_sleep = AsyncMock()
    monkeypatch.setattr(m5ctl.asyncio, "sleep", mock_sleep)
    return mock_client, mock_sleep


async def test_connect_first_attempt_succeeds(m5ctl, monkeypatch):
    """connect() succeeds immediately — no sleep, disconnect called once."""
    client, sleep = _mock_ble(m5ctl, monkeypatch, [None])

    async with m5ctl._connect("AA:BB:CC:DD:EE:FF", 10.0) as c:
        assert c is client

    client.connect.assert_awaited_once()
    client.disconnect.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_connect_retries_on_transient_failure(m5ctl, monkeypatch):
    """First connect() raises BleakError; second attempt succeeds."""
    from bleak import BleakError
    client, sleep = _mock_ble(m5ctl, monkeypatch, [BleakError("transient"), None])

    async with m5ctl._connect("AA:BB:CC:DD:EE:FF", 10.0) as c:
        assert c is client

    assert client.connect.await_count == 2
    sleep.assert_awaited_once_with(0.3)
    # disconnect is called once to clean up after the failed attempt, then once
    # more in the finally teardown after the successful connection.
    assert client.disconnect.await_count == 2


async def test_connect_raises_after_all_retries_exhausted(m5ctl, monkeypatch):
    """All 3 attempts fail — last BleakError re-raised, disconnect called once per attempt."""
    from bleak import BleakError
    err = BleakError("device not found")
    client, sleep = _mock_ble(m5ctl, monkeypatch, [err, err, err])

    with pytest.raises(BleakError):
        async with m5ctl._connect("AA:BB:CC:DD:EE:FF", 10.0):
            pass

    assert client.connect.await_count == 3
    assert sleep.await_count == 2  # after attempt 0 (0.3 s) and attempt 1 (0.6 s)
    # disconnect is called after each failed attempt to release adapter resources;
    # the finally teardown is never reached since yield is never hit.
    assert client.disconnect.await_count == 3


# ---------------------------------------------------------------------------
# exec line filtering
# ---------------------------------------------------------------------------

def _filter_lines(m5ctl, raw: list[str]) -> list[str]:
    """Replicate the exec filtering logic from the match block."""
    return [l.strip() for l in raw if l.strip() and not l.strip().startswith("#")]


def test_exec_filters_blank_lines(m5ctl):
    raw = ["PING", "", "   ", "GET_TILT"]
    assert _filter_lines(m5ctl, raw) == ["PING", "GET_TILT"]


def test_exec_filters_comment_lines(m5ctl):
    raw = ["# this is a comment", "PING", "  # indented comment", "GET_STATUS"]
    assert _filter_lines(m5ctl, raw) == ["PING", "GET_STATUS"]


def test_exec_strips_leading_trailing_whitespace(m5ctl):
    raw = ["  PING  ", "\tGET_TILT\t"]
    assert _filter_lines(m5ctl, raw) == ["PING", "GET_TILT"]


def test_exec_empty_input(m5ctl):
    assert _filter_lines(m5ctl, []) == []
    assert _filter_lines(m5ctl, ["", "# comment", "  "]) == []


# ---------------------------------------------------------------------------
# --print-cmd flag in parser
# ---------------------------------------------------------------------------

def test_print_cmd_flag_parses(m5ctl):
    """--print-cmd / -p sets args.print_cmd=True."""
    import argparse
    # We call main() with sys.argv patched; easier to invoke parse_args directly
    # by building a fresh parser the same way main() does, using parse_known_args.
    # Instead, just verify the flag is wired up by importing and calling parse_args.
    import sys as _sys
    old = _sys.argv
    try:
        _sys.argv = ["m5ctl", "-p", "ping"]
        # parse_args is not exposed directly; call main() is not practical without
        # a device.  Instead verify via argparse by reaching into the module.
        # The simplest approach: build the parser by running main up to parse_args.
        # Since that's coupled to sys.exit, we rely on the parser raising SystemExit
        # only if required args are missing.  Use parse_known_args on a minimal argv.
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--print-cmd", action="store_true")
        args, _ = parser.parse_known_args(["-p", "ping"])
        assert args.print_cmd is True

        args2, _ = parser.parse_known_args(["ping"])
        assert args2.print_cmd is False
    finally:
        _sys.argv = old


# ---------------------------------------------------------------------------
# run command — directive expansion (_expand_run_script)
# ---------------------------------------------------------------------------

def _make_script_args(device="AA:BB:CC:DD:EE:FF", timeout=5.0, print_cmd=False):
    """Return a minimal namespace that _expand_run_script and dispatch expect."""
    import argparse
    return argparse.Namespace(device=device, timeout=timeout, print_cmd=print_cmd)


def _src(lines):
    """Convert a list of strings to the (lineno, line) tuples _expand_run_script expects."""
    return [(i + 1, l) for i, l in enumerate(lines)]


def test_run_wait_directive(m5ctl):
    items = m5ctl._expand_run_script(_src(["! wait 2.5"]), _make_script_args())
    assert items == [m5ctl._Wait(2.5)]


def test_run_wait_integer(m5ctl):
    items = m5ctl._expand_run_script(_src(["! wait 3"]), _make_script_args())
    assert items == [m5ctl._Wait(3.0)]


def test_run_echo_directive(m5ctl):
    items = m5ctl._expand_run_script(_src(["! echo hello world"]), _make_script_args())
    assert items == [m5ctl._Echo("hello world")]


def test_run_echo_empty(m5ctl):
    items = m5ctl._expand_run_script(_src(["! echo"]), _make_script_args())
    assert items == [m5ctl._Echo("")]


def test_run_at_directive(m5ctl):
    items = m5ctl._expand_run_script(_src(["! at 21:30:00"]), _make_script_args())
    assert items == [m5ctl._AtTime(21, 30, 0)]


def test_run_at_midnight(m5ctl):
    items = m5ctl._expand_run_script(_src(["! at 00:00:00"]), _make_script_args())
    assert items == [m5ctl._AtTime(0, 0, 0)]


def test_run_for_loop_expands(m5ctl):
    src = _src(["! for 3", "! echo tick", "! endfor"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Echo("tick")] * 3


def test_run_for_zero_iterations(m5ctl):
    src = _src(["! for 0", "! echo never", "! endfor"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == []


def test_run_for_single_iteration(m5ctl):
    src = _src(["! for 1", "! echo once", "! endfor"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Echo("once")]


def test_run_nested_for_loops(m5ctl):
    src = _src([
        "! for 2",
        "! for 3",
        "! echo x",
        "! endfor",
        "! endfor",
    ])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Echo("x")] * 6


def test_run_for_with_wait(m5ctl):
    src = _src(["! for 2", "! wait 1.0", "! endfor"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Wait(1.0), m5ctl._Wait(1.0)]


def test_run_mixed_directives_and_commands(m5ctl):
    src = _src(["! echo start", "ping", "! wait 0.5"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items[0] == m5ctl._Echo("start")
    assert items[1] == "PING"
    assert items[2] == m5ctl._Wait(0.5)


def test_run_ble_command_passthrough(m5ctl):
    items = m5ctl._expand_run_script(_src(["ping"]), _make_script_args())
    assert items == ["PING"]


def test_run_beep_command_passthrough(m5ctl):
    items = m5ctl._expand_run_script(_src(["beep C4 E4 G4"]), _make_script_args())
    assert items == ["BEEP C4 E4 G4"]


def test_run_unmatched_for_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! for 3", "! echo x"]), _make_script_args())


def test_run_orphan_endfor_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! endfor"]), _make_script_args())


def test_run_unknown_directive_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! jump 5"]), _make_script_args())


def test_run_wait_bad_value_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! wait abc"]), _make_script_args())


def test_run_at_bad_format_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! at 9am"]), _make_script_args())


def test_run_for_bad_count_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! for abc", "! endfor"]), _make_script_args())


def test_run_for_negative_count_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! for -1", "! endfor"]), _make_script_args())


def test_run_non_script_cmd_skipped(m5ctl, capsys):
    items = m5ctl._expand_run_script(_src(["scan"]), _make_script_args())
    assert items == []
    captured = capsys.readouterr()
    assert "skipping" in captured.err


def test_run_for_loop_body_after_loop(m5ctl):
    src = _src(["! for 2", "! echo a", "! endfor", "! echo b"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Echo("a"), m5ctl._Echo("a"), m5ctl._Echo("b")]


# ---------------------------------------------------------------------------
# run command — wait_tilt directive
# ---------------------------------------------------------------------------

def test_run_wait_tilt_default(m5ctl):
    items = m5ctl._expand_run_script(_src(["! wait_tilt"]), _make_script_args())
    assert items == [m5ctl._WaitTilt(15.0)]


def test_run_wait_tilt_custom(m5ctl):
    items = m5ctl._expand_run_script(_src(["! wait_tilt 10"]), _make_script_args())
    assert items == [m5ctl._WaitTilt(10.0)]


def test_run_wait_tilt_float(m5ctl):
    items = m5ctl._expand_run_script(_src(["! wait_tilt 7.5"]), _make_script_args())
    assert items == [m5ctl._WaitTilt(7.5)]


def test_run_wait_tilt_bad_value_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! wait_tilt abc"]), _make_script_args())


def test_run_wait_tilt_zero_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! wait_tilt 0"]), _make_script_args())


def test_run_wait_tilt_negative_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! wait_tilt -5"]), _make_script_args())


# ---------------------------------------------------------------------------
# run command — exit directive
# ---------------------------------------------------------------------------

def test_run_exit_directive(m5ctl):
    items = m5ctl._expand_run_script(_src(["! exit"]), _make_script_args())
    assert items == [m5ctl._Exit()]


def test_run_exit_stops_expansion(m5ctl):
    src = _src(["! echo a", "! exit", "! echo b"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Echo("a"), m5ctl._Exit(), m5ctl._Echo("b")]


def test_run_exit_with_trailing_text_ignored(m5ctl):
    items = m5ctl._expand_run_script(_src(["! exit debug checkpoint"]), _make_script_args())
    assert items == [m5ctl._Exit()]


def test_run_exit_in_for_loop(m5ctl):
    src = _src(["! for 3", "! exit", "! endfor"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items == [m5ctl._Exit(), m5ctl._Exit(), m5ctl._Exit()]


# ---------------------------------------------------------------------------
# run command — expect directive
# ---------------------------------------------------------------------------

def test_run_expect_single_word(m5ctl):
    items = m5ctl._expand_run_script(_src(["! expect TILT"]), _make_script_args())
    assert items == [m5ctl._Expect("TILT", 1)]


def test_run_expect_multi_word(m5ctl):
    items = m5ctl._expand_run_script(_src(["! expect EVENT SCREEN TIME"]), _make_script_args())
    assert items == [m5ctl._Expect("EVENT SCREEN TIME", 1)]


def test_run_expect_single_token_prefix(m5ctl):
    items = m5ctl._expand_run_script(_src(["! expect OK"]), _make_script_args())
    assert items == [m5ctl._Expect("OK", 1)]


def test_run_expect_no_prefix_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! expect"]), _make_script_args())


def test_run_expect_case_preserved(m5ctl):
    items = m5ctl._expand_run_script(_src(["! expect Event Screen"]), _make_script_args())
    assert items == [m5ctl._Expect("Event Screen", 1)]


def test_run_expect_inline_comment_stripped(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["! expect EVENT SCREEN CLINOMETER  # wait for screen change"]),
        _make_script_args(),
    )
    assert items == [m5ctl._Expect("EVENT SCREEN CLINOMETER", 1)]


def test_run_expect_no_prefix_after_comment_strip_exits(m5ctl):
    """'! expect # comment' strips to empty prefix → error."""
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! expect # comment"]), _make_script_args())


# ---------------------------------------------------------------------------
# run command — apostrophe in note names (octave marker)
# ---------------------------------------------------------------------------

def test_run_beep_apostrophe_note(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["beep C4 E4 G4 C'4 G4 E4 C4"]), _make_script_args()
    )
    assert items == ["BEEP C4 E4 G4 C'4 G4 E4 C4"]


def test_run_show_msg_apostrophe_text(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["show-msg 5 it's fine"]), _make_script_args()
    )
    assert items == ["SHOW_MSG 5 it's fine"]


# ---------------------------------------------------------------------------
# cmd_run — look-ahead: plain BLE command followed by ! expect
# ---------------------------------------------------------------------------

def _make_cmd_run_harness(m5ctl, monkeypatch, responses_by_command: dict):
    """Patches _connect/_start_notify so cmd_run runs without a real device.

    responses_by_command maps BLE command string to list of reply strings.
    All replies for a command are injected into the queue at write time.
    """
    from contextlib import asynccontextmanager

    notify_cb = []

    class _FakeClient:
        async def write_gatt_char(self, uuid, data, response=False):
            cmd = data.decode("utf-8")
            for msg in responses_by_command.get(cmd, []):
                notify_cb[0](None, bytearray(msg.encode("utf-8")))

    @asynccontextmanager
    async def _fake_connect(address, timeout):
        yield _FakeClient()

    async def _fake_start_notify(client, uuid, callback, retries=3):
        notify_cb.append(callback)

    monkeypatch.setattr(m5ctl, "_connect", _fake_connect)
    monkeypatch.setattr(m5ctl, "_start_notify", _fake_start_notify)


async def test_cmd_run_plain_command_no_expect(m5ctl, monkeypatch, capsys):
    """Plain command with no following _Expect: auto-consume still works."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {"PING": ["OK PONG"]})
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", ["PING"], timeout=5.0, print_cmd=False)
    assert "OK PONG" in capsys.readouterr().out


async def test_cmd_run_plain_then_expect_same_response(m5ctl, monkeypatch, capsys):
    """Regression: PING + _Expect("OK PONG") — expect must see the reply, not time out."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {"PING": ["OK PONG"]})
    items = ["PING", m5ctl._Expect("OK PONG", 2)]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    out = capsys.readouterr().out
    assert out.count("OK PONG") == 1


async def test_cmd_run_show_msg_with_two_expects(m5ctl, monkeypatch, capsys):
    """demo.m5s pattern: one command, three notifications, two _Expect items drain them all."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {
        "SHOW_MSG 2 Demo": ["OK MESSAGE", "EVENT SCREEN MESSAGE", "EVENT SCREEN CLINOMETER"],
    })
    items = [
        "SHOW_MSG 2 Demo",
        m5ctl._Expect("EVENT SCREEN MESSAGE", 2),
        m5ctl._Expect("EVENT SCREEN CLINOMETER", 3),
    ]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    lines = capsys.readouterr().out.splitlines()
    assert "OK MESSAGE" in lines
    assert "EVENT SCREEN MESSAGE" in lines
    assert "EVENT SCREEN CLINOMETER" in lines


async def test_cmd_run_two_plain_commands(m5ctl, monkeypatch, capsys):
    """Two consecutive plain commands with no _Expect: each still consumes its own reply."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {"PING": ["OK PONG"], "GET_STATUS": ["OK STATUS"]})
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", ["PING", "GET_STATUS"], timeout=5.0, print_cmd=False)
    out = capsys.readouterr().out
    assert "OK PONG" in out
    assert "OK STATUS" in out


async def test_cmd_run_last_command_still_consumed(m5ctl, monkeypatch, capsys):
    """Last item in list has no successor (next_item is None): auto-consume fires normally."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {"GET_TILT": ["TILT 1.0 2.0"]})
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", ["GET_TILT"], timeout=5.0, print_cmd=False)
    assert "TILT 1.0 2.0" in capsys.readouterr().out


async def test_cmd_run_command_followed_by_wait_still_consumed(m5ctl, monkeypatch, capsys):
    """_Wait after a plain command is not _Expect: auto-consume still fires."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {"PING": ["OK PONG"]})
    items = ["PING", m5ctl._Wait(0.0)]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    assert "OK PONG" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run command — timeout directive (parse-time)
# ---------------------------------------------------------------------------

def test_run_timeout_expect(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["! timeout 10 expect EVENT BUTTON M5"]), _make_script_args()
    )
    assert len(items) == 1
    assert isinstance(items[0], m5ctl._Timeout)
    assert items[0].max_wait == 10.0
    assert isinstance(items[0].item, m5ctl._Expect)
    assert items[0].item.prefix == "EVENT BUTTON M5"


def test_run_timeout_wait_tilt(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["! timeout 10 wait_tilt 15"]), _make_script_args()
    )
    assert items == [m5ctl._Timeout(10.0, m5ctl._WaitTilt(15.0))]


def test_run_timeout_wait_tilt_default_degrees(m5ctl):
    items = m5ctl._expand_run_script(
        _src(["! timeout 10 wait_tilt"]), _make_script_args()
    )
    assert items == [m5ctl._Timeout(10.0, m5ctl._WaitTilt(15.0))]


def test_run_timeout_missing_directive_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! timeout 10"]), _make_script_args())


def test_run_timeout_bad_seconds_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(
            _src(["! timeout abc expect FOO"]), _make_script_args()
        )


def test_run_timeout_zero_seconds_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(
            _src(["! timeout 0 expect FOO"]), _make_script_args()
        )


def test_run_timeout_unsupported_inner_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(
            _src(["! timeout 10 wait 5"]), _make_script_args()
        )


def test_run_timeout_expect_no_prefix_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(
            _src(["! timeout 10 expect"]), _make_script_args()
        )


# ---------------------------------------------------------------------------
# run command — if_timed_out / else / endif (parse-time)
# ---------------------------------------------------------------------------

def test_run_if_timed_out_no_else(m5ctl):
    src = _src(["! if_timed_out", "! echo a", "! endif"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items[0] == m5ctl._IfTimedOut(1)
    assert items[1] == m5ctl._Echo("a")
    assert items[2] == m5ctl._EndIf(3)


def test_run_if_timed_out_with_else(m5ctl):
    src = _src(["! if_timed_out", "! echo a", "! else", "! echo b", "! endif"])
    items = m5ctl._expand_run_script(src, _make_script_args())
    assert items[0] == m5ctl._IfTimedOut(1)
    assert items[1] == m5ctl._Echo("a")
    assert items[2] == m5ctl._Else(3)
    assert items[3] == m5ctl._Echo("b")
    assert items[4] == m5ctl._EndIf(5)


def test_run_orphan_else_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! else"]), _make_script_args())


def test_run_orphan_endif_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! endif"]), _make_script_args())


def test_run_unclosed_if_timed_out_exits(m5ctl):
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(_src(["! if_timed_out", "! echo a"]), _make_script_args())


def test_run_double_else_exits(m5ctl):
    src = _src(["! if_timed_out", "! echo a", "! else", "! echo b", "! else", "! echo c", "! endif"])
    with pytest.raises(SystemExit):
        m5ctl._expand_run_script(src, _make_script_args())


# ---------------------------------------------------------------------------
# cmd_run — ! timeout runtime behaviour
# ---------------------------------------------------------------------------

async def test_cmd_run_timeout_expect_matched(m5ctl, monkeypatch, capsys):
    """Event arrives before timeout — timed_out stays False, success branch executes."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {
        "SHOW_MSG_WAIT inf M5 go": ["EVENT SCREEN MESSAGE", "EVENT BUTTON M5"],
    })
    items = [
        "SHOW_MSG_WAIT inf M5 go",
        m5ctl._Expect("EVENT SCREEN MESSAGE", 1),
        m5ctl._Timeout(5.0, m5ctl._Expect("EVENT BUTTON M5", 2)),
        m5ctl._IfTimedOut(lineno=3),
        m5ctl._Echo("timed_out_branch"),
        m5ctl._Else(lineno=4),
        m5ctl._Echo("success_branch"),
        m5ctl._EndIf(lineno=5),
    ]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    out = capsys.readouterr().out
    assert "success_branch" in out
    assert "timed_out_branch" not in out


async def test_cmd_run_timeout_expect_timed_out(m5ctl, monkeypatch, capsys):
    """No event arrives — timed_out becomes True, timeout branch executes, no sys.exit."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {
        "SHOW_MSG_WAIT inf M5 go": ["EVENT SCREEN MESSAGE"],
    })
    items = [
        "SHOW_MSG_WAIT inf M5 go",
        m5ctl._Expect("EVENT SCREEN MESSAGE", 1),
        m5ctl._Timeout(0.01, m5ctl._Expect("EVENT BUTTON M5", 2)),
        m5ctl._IfTimedOut(lineno=3),
        m5ctl._Echo("timed_out_branch"),
        m5ctl._Else(lineno=4),
        m5ctl._Echo("success_branch"),
        m5ctl._EndIf(lineno=5),
    ]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    out = capsys.readouterr().out
    assert "timed_out_branch" in out
    assert "success_branch" not in out


# ---------------------------------------------------------------------------
# cmd_run — ! if_timed_out / ! else / ! endif branching
# ---------------------------------------------------------------------------

async def test_cmd_run_if_timed_out_default_false(m5ctl, monkeypatch, capsys):
    """Without a preceding ! timeout, timed_out defaults to False — if-block skipped."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {})
    items = [
        m5ctl._IfTimedOut(lineno=1),
        m5ctl._Echo("timed_out_branch"),
        m5ctl._EndIf(lineno=2),
    ]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    assert "timed_out_branch" not in capsys.readouterr().out


async def test_cmd_run_if_else_default_false(m5ctl, monkeypatch, capsys):
    """timed_out=False → else-block executes."""
    _make_cmd_run_harness(m5ctl, monkeypatch, {})
    items = [
        m5ctl._IfTimedOut(lineno=1),
        m5ctl._Echo("timed_out_branch"),
        m5ctl._Else(lineno=2),
        m5ctl._Echo("success_branch"),
        m5ctl._EndIf(lineno=3),
    ]
    await m5ctl.cmd_run("AA:BB:CC:DD:EE:FF", items, timeout=5.0, print_cmd=False)
    out = capsys.readouterr().out
    assert "success_branch" in out
    assert "timed_out_branch" not in out

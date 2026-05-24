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
# _load_all_devices — config file parsing
# ---------------------------------------------------------------------------

def test_load_device_addr_raw_mac(m5ctl, monkeypatch, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("device = AA:BB:CC:DD:EE:FF\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_device_addr() == "AA:BB:CC:DD:EE:FF"


def test_load_device_addr_name_alias(m5ctl, monkeypatch, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("device.main = F0:12:34:56:78:D2\ndevice = main\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_device_addr() == "F0:12:34:56:78:D2"


def test_load_device_addr_unknown_alias_returns_none(m5ctl, monkeypatch, tmp_path):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text("device = notfound\n")
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_device_addr() is None


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
])
def test_load_all_devices(m5ctl, monkeypatch, tmp_path, conf_text, expected):
    conf = tmp_path / "m5ctl.conf"
    conf.write_text(conf_text)
    monkeypatch.setattr(m5ctl, "_get_conf_path", lambda: conf)
    assert m5ctl._load_all_devices() == expected


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
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: None)
    assert m5ctl._resolve_device(None) == OTHER_MAC


def test_resolve_none_uses_conf_fallback(m5ctl, monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: MAC)
    assert m5ctl._resolve_device(None) == MAC


def test_resolve_none_returns_none_when_nothing_configured(m5ctl, monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: None)
    assert m5ctl._resolve_device(None) is None


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
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: None)

    await m5ctl.cmd_scan()

    assert "[main]" in capsys.readouterr().out


async def test_scan_annotates_bare_device(m5ctl, monkeypatch, capsys):
    mac = "AA:BB:CC:DD:EE:FF"
    scanner = MagicMock()
    scanner.discover = _fake_discover({mac: _fake_device(mac, "M5-NexStar-Level", -60)})
    monkeypatch.setattr(m5ctl, "BleakScanner", scanner)
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: mac)

    await m5ctl.cmd_scan()

    assert "[device]" in capsys.readouterr().out


async def test_scan_no_annotation_for_unknown(m5ctl, monkeypatch, capsys):
    mac = "AA:BB:CC:DD:EE:FF"
    scanner = MagicMock()
    scanner.discover = _fake_discover({mac: _fake_device(mac, "iPhone", -70)})
    monkeypatch.setattr(m5ctl, "BleakScanner", scanner)
    monkeypatch.setattr(m5ctl, "_load_all_devices", lambda: {})
    monkeypatch.setattr(m5ctl, "_load_device_addr", lambda: None)

    await m5ctl.cmd_scan()

    assert "[" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _connect — retry logic (no real device required)
# ---------------------------------------------------------------------------

def _mock_ble(m5ctl, monkeypatch, connect_side_effect):
    """Patch BleakClient and asyncio.sleep; return (mock_client, mock_sleep)."""
    from bleak import BleakError  # noqa: F401 — ensure importable
    mock_client = MagicMock()
    mock_client.connect = AsyncMock(side_effect=connect_side_effect)
    mock_client.disconnect = AsyncMock()
    monkeypatch.setattr(m5ctl, "BleakClient", lambda *a, **kw: mock_client)
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
    client.disconnect.assert_awaited_once()


async def test_connect_raises_after_all_retries_exhausted(m5ctl, monkeypatch):
    """All 3 attempts fail — last BleakError re-raised, disconnect never called."""
    from bleak import BleakError
    err = BleakError("device not found")
    client, sleep = _mock_ble(m5ctl, monkeypatch, [err, err, err])

    with pytest.raises(BleakError):
        async with m5ctl._connect("AA:BB:CC:DD:EE:FF", 10.0):
            pass

    assert client.connect.await_count == 3
    assert sleep.await_count == 2  # after attempt 0 (0.3 s) and attempt 1 (0.6 s)
    client.disconnect.assert_not_awaited()

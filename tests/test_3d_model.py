"""Unit tests for tests/3d_model.py's CLI banner.

These tests do not require a BLE device or display and run as part of the
default pytest suite.
"""

import importlib.util
import pathlib
import sys

import pytest

_TESTS = pathlib.Path(__file__).parent


@pytest.fixture(scope="module")
def model3d():
    spec = importlib.util.spec_from_file_location("model3d", _TESTS / "3d_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_shows_version(model3d, monkeypatch, capsys, flag):
    monkeypatch.setattr(sys, "argv", ["3d_model.py", flag])
    with pytest.raises(SystemExit):
        model3d.main()
    assert f"3d_model {model3d._VERSION}" in capsys.readouterr().out

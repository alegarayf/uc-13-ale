"""Hermetic tests for the ASDK-13 / ASDK-15 egress gate script.

Derived from spec.md ASDK-13 AC1-AC5. No network, no cluster: the SDK module
and its client are stubbed so every stdout branch and exit code is exercised
locally. The one thing these tests cannot prove is real connectivity -- that is
what running the script on the cluster (T3) is for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from jobs.scripts import check_anthropic_egress as gate  # noqa: E402


class _StubAPIStatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _stub_sdk(version: str = "1.3.0", side_effect=None):
    """Build a stand-in for the `anthropic` module with the exception classes."""
    sdk = MagicMock(name="anthropic")
    sdk.__version__ = version
    sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})
    sdk.APITimeoutError = type("APITimeoutError", (sdk.APIConnectionError,), {})
    sdk.APIStatusError = _StubAPIStatusError

    client = MagicMock(name="client")
    client.messages.create.side_effect = side_effect
    sdk.Anthropic.return_value = client
    return sdk, client


@pytest.fixture
def _key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    monkeypatch.delenv("anthropic_secret_scope", raising=False)


# --- AC5: import collision --------------------------------------------------


def test_import_failure_reports_and_exits_nonzero(capsys):
    with patch.object(gate, "_import_anthropic", side_effect=ImportError("no httpx2")):
        assert gate.main() == 1
    assert "ANTHROPIC_IMPORT_FAILED ImportError: no httpx2" in capsys.readouterr().out


# --- AC1 + AC3: both models reachable ---------------------------------------


def test_both_models_ok_exits_zero(capsys, _key):
    sdk, client = _stub_sdk()
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        assert gate.main() == 0
    out = capsys.readouterr().out
    assert "ANTHROPIC_EGRESS_OK claude-sonnet-4-6" in out
    assert "ANTHROPIC_EGRESS_OK claude-haiku-4-5" in out
    assert [c.kwargs["model"] for c in client.messages.create.call_args_list] == [
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ]


# --- AC2: network blocked ---------------------------------------------------


def test_connection_error_reports_blocked_and_exits_nonzero(capsys, _key):
    sdk, _ = _stub_sdk()
    sdk.Anthropic.return_value.messages.create.side_effect = sdk.APIConnectionError(
        "name resolution failed"
    )
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        assert gate.main() == 1
    out = capsys.readouterr().out
    assert "ANTHROPIC_EGRESS_BLOCKED claude-sonnet-4-6" in out
    assert "name resolution failed" in out
    assert "ANTHROPIC_EGRESS_OK" not in out


# --- SPEC_DEVIATION branch: API answered with an error status ---------------


def test_http_error_status_reports_reachable_not_blocked(capsys, _key):
    sdk, _ = _stub_sdk()
    sdk.Anthropic.return_value.messages.create.side_effect = _StubAPIStatusError(
        "invalid x-api-key", 401
    )
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        assert gate.main() == 1
    out = capsys.readouterr().out
    assert "ANTHROPIC_EGRESS_REACHABLE claude-sonnet-4-6 status=401" in out
    assert "ANTHROPIC_EGRESS_BLOCKED" not in out


# --- AC4: version reported, autolog range decided ---------------------------


def test_reports_sdk_version_and_autolog_unsupported_for_1_3_0(capsys, _key):
    sdk, _ = _stub_sdk(version="1.3.0")
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        gate.main()
    assert "ANTHROPIC_SDK_VERSION 1.3.0 autolog_supported=False" in capsys.readouterr().out


def test_reports_autolog_supported_for_version_inside_range(capsys, _key):
    sdk, _ = _stub_sdk(version="0.107.1")
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        gate.main()
    assert "ANTHROPIC_SDK_VERSION 0.107.1 autolog_supported=True" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.54.9", False),   # below the tested floor
        ("0.55.0", True),    # exact floor
        ("0.107.1", True),   # exact ceiling
        ("0.107.2", False),  # just above the ceiling
        ("1.3.0", False),    # the version this project installs
        ("unknown", False),  # unparseable -> never claim support
    ],
)
def test_autolog_supported_boundaries(version, expected):
    assert gate.autolog_supported(version) is expected


# --- Credential handling ----------------------------------------------------


def test_missing_credential_names_scope_and_env_var_without_leaking(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sdk, _ = _stub_sdk()
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        assert gate.main() == 1
    out = capsys.readouterr().out
    assert "ANTHROPIC_CREDENTIAL_MISSING" in out
    assert "anthropic_api_key" in out
    assert "uc13" in out
    assert "ANTHROPIC_API_KEY" in out
    sdk.Anthropic.assert_not_called()


def test_api_key_value_never_appears_in_output(capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value-xyz")
    sdk, _ = _stub_sdk()
    sdk.Anthropic.return_value.messages.create.side_effect = sdk.APIConnectionError(
        "blocked"
    )
    with patch.object(gate, "_import_anthropic", return_value=sdk):
        gate.main()
    assert "sk-ant-secret-value-xyz" not in capsys.readouterr().out

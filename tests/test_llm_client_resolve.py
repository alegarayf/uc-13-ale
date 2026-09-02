"""Hermetic tests for llm_client's backend resolution and alias mapping.

Derived from spec.md ASDK-02 and ASDK-03 (T4 "Done when"). Pure functions,
no I/O, no mocking needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import llm_client  # noqa: E402


# --- resolve_model: both known aliases (ASDK-02 AC2) ------------------------


@pytest.mark.parametrize(
    ("alias", "expected_model_id"),
    [
        ("databricks-claude-sonnet-4-6", "claude-sonnet-4-6"),
        ("databricks-claude-haiku-4-5", "claude-haiku-4-5"),
    ],
)
def test_resolve_model_known_aliases(alias, expected_model_id):
    assert llm_client.resolve_model(alias) == expected_model_id


# --- resolve_model: unknown alias (ASDK-03 AC3) -----------------------------


def test_resolve_model_unknown_alias_raises_value_error_naming_it():
    with pytest.raises(ValueError, match="databricks-claude-opus-9"):
        llm_client.resolve_model("databricks-claude-opus-9")


def test_resolve_model_does_not_derive_via_string_manipulation():
    """A plausible-looking but unmapped alias must not resolve by accident.

    If resolve_model ever regressed to `alias.replace("databricks-", "")`,
    this alias would silently resolve to "claude-opus-9-typo" instead of
    raising -- exactly the failure mode ASDK-03 exists to prevent.
    """
    with pytest.raises(ValueError):
        llm_client.resolve_model("databricks-claude-opus-9-typo")


# --- _active_backend: default (ASDK-02 AC4) ---------------------------------


def test_active_backend_defaults_to_anthropic_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert llm_client._active_backend() == "anthropic"


def test_active_backend_reads_databricks_explicitly(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "databricks")
    assert llm_client._active_backend() == "databricks"


# --- _active_backend: invalid value -----------------------------------------


def test_active_backend_invalid_value_raises_naming_valid_values(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openai")
    with pytest.raises(ValueError, match="openai") as exc_info:
        llm_client._active_backend()
    assert "anthropic" in str(exc_info.value)
    assert "databricks" in str(exc_info.value)

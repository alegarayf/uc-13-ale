"""Hermetic tests for llm_client._normalize_usage.

Derived from spec.md ASDK-11 AC1 (T5 "Done when"). `_normalize_usage` must
produce the exact dict shape agent_base.accumulate_tokens already consumes:
{"prompt_tokens", "completion_tokens", "total_tokens"}.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import llm_client  # noqa: E402


def test_normalize_usage_full_payload():
    usage = SimpleNamespace(input_tokens=120, output_tokens=45)
    assert llm_client._normalize_usage(usage) == {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
    }


def test_normalize_usage_partial_payload_missing_output_tokens():
    """Anthropic's Usage carries optional fields as None; a caller reading
    only some of them (or a stub missing an attribute) must not raise."""
    usage = SimpleNamespace(input_tokens=100)
    assert llm_client._normalize_usage(usage) == {
        "prompt_tokens": 100,
        "completion_tokens": 0,
        "total_tokens": 100,
    }


def test_normalize_usage_empty_payload_defaults_to_zero():
    usage = SimpleNamespace()
    assert llm_client._normalize_usage(usage) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_normalize_usage_none_valued_fields_treated_as_zero():
    """Anthropic's Usage model sets unset optional fields to None, not absent
    -- input_tokens/output_tokens themselves are always populated by the API,
    but this guards the same tolerance if a stub sets them to None."""
    usage = SimpleNamespace(input_tokens=None, output_tokens=30)
    assert llm_client._normalize_usage(usage) == {
        "prompt_tokens": 0,
        "completion_tokens": 30,
        "total_tokens": 30,
    }

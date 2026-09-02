"""Hermetic tests for llm_client._to_anthropic_content.

Derived from spec.md ASDK-09 AC2/AC3 (T6 "Done when"). The exact input shape
mirrors what jobs/scripts/ingestion_parser.py:757 builds today:
[{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
 {"type": "text", "text": "..."}]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import llm_client  # noqa: E402


# --- data-URI -> Anthropic image block --------------------------------------


def test_data_uri_converts_to_anthropic_image_block():
    content = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
    ]
    assert llm_client._to_anthropic_content(content) == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
        }
    ]


# --- order preservation + text passthrough (ASDK-09 AC2) -------------------


def test_preserves_block_order_with_image_first_then_text():
    """Mirrors the exact shape ingestion_parser.py builds: image block first,
    prompt text block second."""
    content = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,WFla"}},
        {"type": "text", "text": "Extract the table."},
    ]
    result = llm_client._to_anthropic_content(content)
    assert result == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "WFla"},
        },
        {"type": "text", "text": "Extract the table."},
    ]


def test_text_only_blocks_pass_through_unaltered():
    content = [{"type": "text", "text": "no image here"}]
    assert llm_client._to_anthropic_content(content) == content


# --- str wraps to a single text block ---------------------------------------


def test_str_input_wraps_in_single_text_block():
    assert llm_client._to_anthropic_content("hello") == [
        {"type": "text", "text": "hello"}
    ]


# --- malformed data-URI raises, naming the offending block ------------------


def test_malformed_data_uri_raises_value_error_naming_the_block():
    content = [{"type": "image_url", "image_url": {"url": "not-a-data-uri"}}]
    with pytest.raises(ValueError, match="not-a-data-uri"):
        llm_client._to_anthropic_content(content)

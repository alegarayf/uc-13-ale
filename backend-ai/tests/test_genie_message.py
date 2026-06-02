from types import SimpleNamespace

import pytest

from app.services.genie_message import (
    GenieMessageError,
    display_summary_from_genie_text,
    extract_genie_response_text,
)


def test_extract_genie_response_text_from_attachments():
    message = SimpleNamespace(
        content="You are an experienced rules engine developer...",  # echoed user prompt
        attachments=[
            SimpleNamespace(
                text=SimpleNamespace(
                    content="This rule filters out opportunities with ARR below one million dollars."
                ),
                query=None,
            )
        ],
    )
    assert "ARR below" in extract_genie_response_text(message)


def test_extract_genie_response_text_requires_attachment():
    message = SimpleNamespace(content="Only the user question is here", attachments=[])
    with pytest.raises(GenieMessageError):
        extract_genie_response_text(message)


def test_sanitize_summary_removes_question_lines():
    text = """This rule excludes opportunities below $1M ARR.

Would you like to specify which ARR field to use?

Healthcare exceptions apply when growth exceeds 40%."""
    shown = display_summary_from_genie_text(text)
    assert "Would you like" not in shown
    assert "below $1M" in shown
    assert "Healthcare" in shown


def test_display_summary_strips_json_block():
    text = """Here is the rule interpretation.

```json
{"summary":"hidden","rule":{}}
```

Focus on B2B SaaS only."""
    shown = display_summary_from_genie_text(text)
    assert "hidden" not in shown
    assert "B2B SaaS" in shown

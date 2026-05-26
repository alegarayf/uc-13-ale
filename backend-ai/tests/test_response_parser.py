import pytest

from app.services.response_parser import ParseError, parse_rules_interpretation


def test_parse_canonical_json_object():
    text = """{"summary":"Reject deals under $1M ARR.","rule":{"name":"Min ARR","conditions":[]}}"""
    summary, config = parse_rules_interpretation(text)
    assert "under $1M" in summary
    assert config["name"] == "Min ARR"


def test_parse_single_quoted_python_dict():
    text = """{'summary': 'Reject small deals.', 'rule': {'name': 'Size floor', 'conditions': []}}"""
    summary, config = parse_rules_interpretation(text)
    assert "small deals" in summary
    assert config["name"] == "Size floor"


def test_parse_legacy_markdown_format():
    text = """## Summary
Reject deals under $1M ARR.

## Rule configuration
```json
{"name": "Min ARR", "conditions": []}
```
"""
    summary, config = parse_rules_interpretation(text)
    assert "under $1M" in summary
    assert config["name"] == "Min ARR"


def test_parse_prefers_last_canonical_json_when_multiple_present():
    text = """
Here is an example from the instructions:
{"summary":"Reject opportunities below $1M ARR unless healthcare with high growth.","rule":{"name":"Example","conditions":[]}}

And here is the actual answer:
{"summary":"Only accept B2B SaaS companies with NDR above 120%.","rule":{"name":"SaaS NDR gate","conditions":[]}}
"""
    summary, config = parse_rules_interpretation(text)
    assert "SaaS" in summary
    assert config["name"] == "SaaS NDR gate"


def test_parse_requires_content():
    with pytest.raises(ParseError):
        parse_rules_interpretation("   ")

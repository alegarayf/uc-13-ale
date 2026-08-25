"""Source scan: BMA _USER_PROMPT_TEMPLATE puts executive_summary first (C36).

Does not import the agent module. No live Spark/warehouse.
"""

from __future__ import annotations

from pathlib import Path

_AGENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "databricks"
    / "agents"
    / "workstreams"
    / "business_model_agent.py"
)

_INSTRUCTION = (
    "<5–6 sentence factual summary covering: (1) what the company does and at "
    "what revenue scale; (2) how it earns revenue and the margin profile; "
    "(3) who leads the company and any ownership/key-man context; "
    "(4) workforce model and delivery capacity; (5) customer stickiness "
    "signal from tenure or utilization data; (6) what has changed recently. "
    "Use numbers where stated.>"
)


def _user_prompt_source() -> str:
    source = _AGENT_PATH.read_text(encoding="utf-8")
    start = source.find("_USER_PROMPT_TEMPLATE")
    assert start != -1, "_USER_PROMPT_TEMPLATE not found"
    end = source.find('_VALID_REVENUE_TAGS', start)
    assert end != -1, "template end marker not found"
    return source[start:end]


def test_bma_executive_summary_is_first_top_level_key() -> None:
    template = _user_prompt_source()
    # Source form: skeleton opens with `{{` then two-space "executive_summary".
    opener = template.find("\n{{\n")
    assert opener != -1, "JSON skeleton opening {{ not found"
    after_opener = template[opener + len("\n{{\n") :]
    assert after_opener.startswith('  "executive_summary":'), (
        "executive_summary is not the first top-level skeleton key"
    )
    closer = after_opener.rfind("\n}}")
    assert closer != -1, "JSON skeleton closing }} not found"
    skeleton_body = after_opener[:closer]
    top_level = []
    for line in skeleton_body.splitlines():
        if line.startswith('  "') and '":' in line[3:]:
            top_level.append(line[3 : line.index('":', 3)])
    assert top_level, "no top-level skeleton keys found"
    assert top_level[0] == "executive_summary"
    assert top_level.count("executive_summary") == 1
    assert top_level[-1] == "extraction_notes"
    cit_idx = top_level.index("citations")
    notes_idx = top_level.index("extraction_notes")
    assert "executive_summary" not in top_level[cit_idx + 1 : notes_idx]
    assert _INSTRUCTION in template
    assert template.count(_INSTRUCTION) == 1

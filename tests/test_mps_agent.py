"""Unit tests for agents.workstreams.mps_agent — MPSAgent (T3, T5).

docs/plans/mps_score/tasks/T3_agente_prompt.md and
docs/plans/mps_score/tasks/T5_retrieval_persistencia.md, tests 8-13 of
docs/plans/mps_score/mps_score_1st_draft.md §11. LLM calls are mocked by
monkeypatching the ``MPSAgent`` instance's ``_call_llm`` — same pattern as
tests/test_rainmaker_narrative.py:130 (subclass/stub + monkeypatch), applied
directly to the instance since MPSAgent (unlike the narrative layer's
``_RainmakerNarrativeLlm`` shim) is itself the full agent (§4.2).

Test 10 was rewritten in T5, not extended (its T3 version pinned "zero
calls in both branches" — the correct pin for T3's scope, which excluded
retrieval entirely; T5 flips the ``cim_detected=False`` case to "exactly
one call"). Test 13 (Delta write) is static/AST-based, following
tests/test_legal_contracts_agent.py's precedent: it cannot execute real
DDL against a Spark stub, so it checks that ``_EXPECTED_COLS`` matches the
``_CREATE_TABLE_SQL`` column set — the DDL itself needs verification
against the SQL warehouse (T6).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

from agents.exec_summary.mps_rubric import RubricError, load_rubric
from agents.workstreams.mps_agent import (
    MPSAgent,
    _assemble_system_prompt,
    _rationale_is_near_copy,
)

_FIXTURE_NAMES = ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"]


def _bundle(**overrides) -> dict:
    base = {
        "meta": {"vertical_overlay": "healthcare_services", "company_name": "Acme"},
        "executive": {"in_one_line": "A thing that does a thing.", "thesis_bullets": ["Bullet A"]},
        "company_framing": {
            "overview_bullets": ["Founded 2020"],
            "revenue_model": {"tag": "subscription", "quality_flag": "durable", "note": "Recurring."},
            "workforce_notes": "Aggregate workforce model: offshore 40% of total.",
            "recent_changes": [
                {"change_type": "ma", "description": "Acquired Acme Home Care (2024)"},
                {"change_type": "staffing", "description": "Hired a new COO"},
            ],
        },
        "revenue_quality": {"scale_narrative": "Scale narrative."},
        "kpi_dashboard": [{"display_name": "ARR", "stated_value": "$5M"}],
        "risks": [],
        "data_room_gaps": [],
        "financials": {"table_rows": [{"year": "2024A", "revenue": "$5.0", "ebitda": "$1.0"}]},
        "confidence_by_area": {"business_model": "medium"},
        "legal": {
            "section_confidence": "medium",
            "top_flags": [{"metric": "coc_consent_required", "note": "CoC consent required."}],
            "top_gaps": ["Litigation exposure"],
        },
        "qoe": {
            "addback_pct_of_ebitda": "50.0",
            "tier_summary": "Some addbacks.",
            "flags": [{"metric": "tier4_addback", "note": "Tier 4 addback flagged."}],
        },
    }
    base.update(overrides)
    return base


def _valid_categories_payload(rubric: dict, **per_category_overrides) -> dict:
    categories = []
    for category in rubric["categories"]:
        row = {
            "key": category["key"],
            "score": 3,
            "rationale": f"Concrete concern for {category['key']} grounded in the digest.",
            "counter_evidence": "",
            "sub_axis_notes": [],
            "confidence": "medium",
        }
        row.update(per_category_overrides.get(category["key"], {}))
        categories.append(row)
    return {"categories": categories}


def _score_kwargs(**overrides) -> dict:
    kwargs = dict(
        bundle=_bundle(),
        catalog="uc13",
        company_name="Acme",
        spark=None,
        llm_endpoint="fake-endpoint",
        run_mode="cim_only",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Test 8 — degradation
# ---------------------------------------------------------------------------


def test_llm_exception_degrades_without_raising(monkeypatch):
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("simulated timeout")))
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "degraded"
    assert result["categories"] == []
    assert result["total"] is None
    assert result["verdict"] is None
    assert result["degraded_reason"]


def test_llm_non_json_response_degrades(monkeypatch):
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: "not valid json {{{")
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "degraded"


def test_llm_response_missing_categories_key_entirely_degrades(monkeypatch):
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps({"not_categories": []}))
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "degraded"


@pytest.mark.parametrize("bad_score", [0, 7])
def test_llm_score_out_of_range_degrades_whole_result(monkeypatch, bad_score):
    rubric = load_rubric()
    payload = _valid_categories_payload(rubric)
    payload["categories"][0]["score"] = bad_score
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(payload))
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "degraded"


def test_rubric_load_failure_degrades(monkeypatch):
    monkeypatch.setattr(
        "agents.workstreams.mps_agent.load_rubric",
        lambda: (_ for _ in ()).throw(RubricError("boom")),
    )
    agent = MPSAgent()
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "degraded"
    assert "boom" in result["degraded_reason"]


def test_missing_category_key_scores_none_without_shifting_the_list(monkeypatch):
    """§4.1's non-negotiable rule: a key missing from the LLM's response
    scores None for THAT category, without shifting the other six — the
    result status is 'partial' (total is None because a partial product is
    meaningless), not 'degraded'.

    This intentionally diverges from mps_score_1st_draft.md §11 test 8's
    shorthand ("returns 6 categories ... -> degraded", line 583), which
    conflicts with the same document's own §4.1 validation table (lines
    292-304: "key faltante -> score: None para esa categoria, sin desplazar
    la lista") and with T3_agente_prompt.md's "No negociables" section
    (lines 34-37), which states the missing-key rule explicitly and labels
    it non-negotiable. Per docs/plans/mps_score/tasks/00_common.md rule 4,
    following the more specific/authoritative rule instead of splitting the
    difference.
    """
    rubric = load_rubric()
    payload = _valid_categories_payload(rubric)
    dropped_key = payload["categories"][0]["key"]
    payload["categories"] = payload["categories"][1:]

    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(payload))
    result = agent.score(**_score_kwargs())

    assert result["mps_status"] == "partial"
    assert result["total"] is None
    assert result["verdict"] is None
    assert len(result["categories"]) == 7
    assert [c["key"] for c in result["categories"]] == [c["key"] for c in rubric["categories"]]
    missing_row = next(c for c in result["categories"] if c["key"] == dropped_key)
    assert missing_row["score"] is None


def test_unknown_category_key_is_dropped_not_degraded(monkeypatch):
    rubric = load_rubric()
    payload = _valid_categories_payload(rubric)
    payload["categories"].append({"key": "not_a_real_category", "score": 5, "rationale": "x"})
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(payload))
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "success"
    assert len(result["categories"]) == 7
    assert "not_a_real_category" not in [c["key"] for c in result["categories"]]


def test_successful_call_produces_seven_categories_in_rubric_order(monkeypatch):
    rubric = load_rubric()
    payload = _valid_categories_payload(rubric)
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(payload))
    result = agent.score(**_score_kwargs())
    assert result["mps_status"] == "success"
    assert [c["key"] for c in result["categories"]] == [c["key"] for c in rubric["categories"]]
    assert result["total"] == pytest.approx(3**7 / 1000)
    assert result["verdict"] in ("above threshold", "below threshold — requires explicit override rationale to advance")


# ---------------------------------------------------------------------------
# Test 9 — prompt contract
# ---------------------------------------------------------------------------


def test_prompt_contains_verbatim_definitions_and_calibration_rules():
    rubric = load_rubric()
    prompt = _assemble_system_prompt(rubric)
    normalized_prompt = " ".join(prompt.split())

    for category in rubric["categories"]:
        definition = " ".join(category["definition"].split())
        assert definition in normalized_prompt, f"{category['key']} definition not verbatim in prompt"

    for rule in rubric["calibration_rules"]:
        assert rule["key"] in prompt
        rule_text = " ".join(rule["text"].split())
        assert rule_text in normalized_prompt, f"{rule['key']} text not verbatim in prompt"


def test_prompt_never_reveals_threshold_or_total_formula():
    rubric = load_rubric()
    prompt = _assemble_system_prompt(rubric)
    lowered = prompt.lower()

    assert "mps_total" not in lowered
    assert "product(scores)" not in lowered
    assert "/1000" not in lowered.replace(" ", "")
    assert "/ 1000" not in lowered

    threshold = rubric["threshold"]
    assert f"threshold is {threshold}" not in lowered
    assert f"threshold: {threshold}" not in lowered
    assert f"threshold of {threshold}" not in lowered
    assert "mps_verdict" not in lowered


# ---------------------------------------------------------------------------
# Test 10 — retrieval gating (§7.4/§A.3b — rewritten in T5)
# ---------------------------------------------------------------------------


class _FakeSpark:
    """Stands in for a real SparkSession so ``spark is not None`` — enough
    to clear the agent's no-session guard. The stubbed
    ``semantic_search_with_fallback`` below never actually touches it."""


def _bundle_with_cim_marker(detected: bool) -> dict:
    return _bundle(meta={"basis_of_preparation": f"cim_detected={detected}"})


def test_growth_mindset_retrieval_skipped_when_cim_detected(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "agents.workstreams.mps_agent.semantic_search_with_fallback",
        lambda *a, **k: calls.append((a, k)),
    )
    rubric = load_rubric()
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(_valid_categories_payload(rubric)))

    result = agent.score(
        **_score_kwargs(bundle=_bundle_with_cim_marker(True), spark=_FakeSpark(), run_mode="cim_only")
    )

    assert calls == []
    assert result["cim_detected"] is True
    assert result["retrieval_used"] is False


def test_growth_mindset_retrieval_runs_exactly_once_when_no_cim(monkeypatch):
    calls = []

    def _fake_search(**kwargs):
        calls.append(kwargs)
        return _EmptyRouteResult(), False

    monkeypatch.setattr("agents.workstreams.mps_agent.semantic_search_with_fallback", _fake_search)
    rubric = load_rubric()
    agent = MPSAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *a, **k: json.dumps(_valid_categories_payload(rubric)))

    result = agent.score(
        **_score_kwargs(
            bundle=_bundle_with_cim_marker(False), spark=_FakeSpark(), run_mode="full_vdr_no_cim"
        )
    )

    assert len(calls) == 1
    assert calls[0]["company_name"] == "Acme"
    assert result["cim_detected"] is False
    assert result["retrieval_used"] is True


class _EmptyRouteResult:
    chunks: list = []


# ---------------------------------------------------------------------------
# Test 11 — generalization across all 5 bundle fixtures
# ---------------------------------------------------------------------------


def _load_fixture_bundle(name: str) -> dict:
    with open(f"tests/fixtures/{name}_bundle.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_generalizes_across_all_five_fixtures_without_cross_contamination(monkeypatch):
    rubric = load_rubric()
    agent = MPSAgent()
    per_fixture: list[tuple[str, list[str]]] = []

    for name in _FIXTURE_NAMES:
        bundle = _load_fixture_bundle(name)
        company = str((bundle.get("meta") or {}).get("company_name") or name)
        payload = {
            "categories": [
                {
                    "key": category["key"],
                    "score": 3,
                    "rationale": f"{company} shows a concrete, named concern for {category['key']}.",
                    "counter_evidence": "",
                    "sub_axis_notes": [],
                    "confidence": "medium",
                }
                for category in rubric["categories"]
            ]
        }
        monkeypatch.setattr(agent, "_call_llm", lambda *a, payload=payload, **k: json.dumps(payload))
        result = agent.score(
            bundle=bundle,
            catalog="uc13",
            company_name=company,
            spark=None,
            llm_endpoint="fake-endpoint",
            run_mode="cim_only",
        )
        assert result["mps_status"] == "success", f"{name} did not score successfully"
        assert len(result["categories"]) == 7
        for cat in result["categories"]:
            assert cat["rationale"], f"{name}/{cat['key']} has an empty rationale"
        per_fixture.append((company, [c["rationale"] for c in result["categories"]]))

    for i, (company, _rationales) in enumerate(per_fixture):
        for j, (other_company, other_rationales) in enumerate(per_fixture):
            if i == j or company == other_company:
                continue
            for rationale in other_rationales:
                assert company not in rationale, (
                    f"{company!r} leaked into a rationale generated for {other_company!r}"
                )


# ---------------------------------------------------------------------------
# Test 12 — R-C guard (weak but cheap, per plan §11)
# ---------------------------------------------------------------------------


def test_rc_guard_flags_a_near_copy_rationale_but_not_a_grounded_one():
    rubric = load_rubric()
    category = rubric["categories"][0]

    assert _rationale_is_near_copy(category["definition"], category["definition"])

    grounded = "Gross margin runs 6 points above the two named regional competitors per the CIM."
    assert not _rationale_is_near_copy(grounded, category["definition"])


# ---------------------------------------------------------------------------
# Test 13 — Delta write, _EXPECTED_COLS guard (§9)
#
# Static/AST-based, following tests/test_legal_contracts_agent.py's
# precedent (test_expected_cols_matches_appendix_a /
# test_create_legal_table_ddl_columns_match_expected_cols): a Spark stub
# cannot execute real DDL, so it cannot catch the cold-start-only DEFAULT/
# TBLPROPERTIES class of bug databricks/CLAUDE.md documents. What it can
# verify without a Spark session at all is that the migration guard's
# source of truth (_EXPECTED_COLS) and the actual write schema/DDL agree.
# The DDL itself needs verification against the SQL warehouse (T6).
# ---------------------------------------------------------------------------

_MPS_AGENT_PATH = Path(__file__).resolve().parents[1] / "databricks" / "agents" / "workstreams" / "mps_agent.py"
_MPS_AGENT_SOURCE = _MPS_AGENT_PATH.read_text(encoding="utf-8")

_MPS_SCORE_EXPECTED_COLS = {
    "company_name",
    "catalog",
    "generated_at",
    "run_mode",
    "rubric_version",
    "total",
    "threshold",
    "verdict",
    "mps_status",
    "categories_json",
    "cim_detected",
    "retrieval_used",
    "llm_endpoint",
    "run_id",
}


def _extract_mps_module_constant(name: str) -> str:
    tree = ast.parse(_MPS_AGENT_SOURCE)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.get_source_segment(_MPS_AGENT_SOURCE, node.value) or ""
    raise AssertionError(f"constant {name} not found in mps_agent.py")


def _ddl_column_names(ddl: str) -> set[str]:
    body = ddl.split("(", 1)[1].rsplit(")", 1)[0]
    return {
        line.strip().split()[0]
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    }


def test_expected_cols_matches_plan_section_9():
    segment = _extract_mps_module_constant("_EXPECTED_COLS")
    cols = set(re.findall(r'"([^"]+)"', segment))
    assert cols == _MPS_SCORE_EXPECTED_COLS


def test_create_mps_score_table_ddl_columns_match_expected_cols():
    ddl_template = _extract_mps_module_constant("_CREATE_TABLE_SQL")
    ddl_cols = _ddl_column_names(ddl_template.format(table="uc13_ale.analysis.mps_score"))
    assert ddl_cols == _MPS_SCORE_EXPECTED_COLS


def test_mps_score_table_ddl_has_no_default_clause():
    """databricks/CLAUDE.md: a DEFAULT clause needs the
    `delta.feature.allowColumnDefaults` TBLPROPERTIES opt-in or CREATE TABLE
    fails on cold start. mps_score has no DEFAULT, so it needs none — this
    pins that so a future column addition doesn't introduce one silently."""
    ddl_template = _extract_mps_module_constant("_CREATE_TABLE_SQL")
    assert "DEFAULT" not in ddl_template.upper()
    assert "TBLPROPERTIES" not in ddl_template.upper()


def test_run_mode_column_has_no_check_constraint():
    """§5.1/§9 non-negotiable: run_mode is a plain STRING so the third mode
    can be persisted later without a migration."""
    ddl_template = _extract_mps_module_constant("_CREATE_TABLE_SQL")
    for line in ddl_template.splitlines():
        if line.strip().startswith("run_mode"):
            assert "CHECK" not in line.upper()
            assert line.strip().split()[1].upper().rstrip(",") == "STRING"
            return
    raise AssertionError("run_mode column not found in _CREATE_TABLE_SQL")


def test_delta_write_is_append_only_never_overwrite():
    """§9 non-negotiable: append-only, never overwrite — score history from
    day one is what makes a future trend view a rendering change, not a
    migration. Also must never DELETE before writing (that would defeat
    append-only just as surely as an overwrite mode)."""
    body = _MPS_AGENT_SOURCE[_MPS_AGENT_SOURCE.index("def _write_mps_row") :]
    body = body[: body.index("\n\n\n")] if "\n\n\n" in body else body
    assert '.mode("append")' in body
    assert ".mode(\"overwrite\")" not in body
    assert "DELETE FROM" not in body

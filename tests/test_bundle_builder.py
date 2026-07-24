"""Unit tests for BundleBuilder and GapAggregator (M2 T3, T7)."""

from __future__ import annotations

import json
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agents.orchestrator.bundle_builder import (
    BundleBuilder,
    GapAggregator,
    _EXECUTIVE_LLM_NARRATIVE_KEYS,
    _EXECUTIVE_LLM_SYSTEM_PROMPT,
    _EXECUTIVE_SYNTHESIS_BUNDLE_SECTION_KEYS,
    _PRELIMINARY_DIGEST_SECTION_TAGS,
    _executive_synthesis_bundle_context,
    _executive_synthesis_gap_context,
    _merge_executive_llm_narrative,
    merge_risks_from_flags,
    synthesize_executive_narrative,
)
from agents.orchestrator.constants import AGENTS_PRESENT_KEYS
from agents.orchestrator.validate import BundleValidationError, validate_bundle

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ELDER_CARE_SNAPSHOTS = _FIXTURES / "elder_care_agent_snapshots.yaml"


def _load_elder_care_snapshots() -> dict:
    with open(_ELDER_CARE_SNAPSHOTS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _enter_build_patches(stack: ExitStack, snapshots: dict | None = None) -> None:
    snapshots = snapshots or {
        "business_model": {
            "delta_row": {"flags": [], "data_room_gaps": []},
            "yaml_dict": {"executive_summary": "Test co"},
            "report_path": "/Volumes/uc13/analysis/reports/Elder_Care/business_model.yaml",
        },
    }
    stack.enter_context(
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value=snapshots,
        )
    )
    stack.enter_context(
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value={"industry_overlay": "healthcare"},
        )
    )
    stack.enter_context(
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        )
    )
    stack.enter_context(
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        )
    )


def test_gap_aggregator_dedupes_on_normalized_text_and_source_agent() -> None:
    agg = GapAggregator()
    snapshots = {
        "legal": {
            "delta_row": {
                "data_room_gaps": [
                    "Missing CoC document",
                    "missing coc document",
                ],
            },
        },
    }
    gaps = agg.merge_data_room_gaps(snapshots)
    assert len(gaps) == 1
    assert gaps[0]["source_agent"] == "legal"


def test_gap_aggregator_keeps_same_text_from_different_agents() -> None:
    agg = GapAggregator()
    snapshots = {
        "kpi": {"delta_row": {"data_room_gaps": ["Missing census data"]}},
        "legal": {"delta_row": {"data_room_gaps": ["Missing census data"]}},
    }
    gaps = agg.merge_data_room_gaps(snapshots)
    assert len(gaps) == 2
    agents = {g["source_agent"] for g in gaps}
    assert agents == {"kpi", "legal"}


def test_merge_risks_from_flags_sorts_critical_first() -> None:
    snapshots = {
        "financial_trends": {
            "delta_row": {
                "flags": [
                    {"severity": "Green", "metric": "Track metric"},
                    {"severity": "Red", "metric": "Critical metric"},
                ],
            },
        },
    }
    risks = merge_risks_from_flags(snapshots)
    assert risks[0]["severity"] == "critical"
    assert len(risks) <= 8


def test_bundle_builder_sets_production_meta_and_provenance() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    minimal_snapshots = {
        "business_model": {
            "delta_row": {"flags": [], "data_room_gaps": []},
            "yaml_dict": {"executive_summary": "Test co"},
            "report_path": "/Volumes/uc13/analysis/reports/Elder_Care/business_model.yaml",
        },
    }

    with (
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value=minimal_snapshots,
        ),
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value={"industry_overlay": "healthcare"},
        ),
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        ),
        patch(
            "agents.orchestrator.bundle_builder.validate_bundle",
        ) as mock_validate,
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        ) as mock_write,
    ):
        bundle = builder.build("Elder Care", "uc13_ale", spark=mock_spark)

    assert bundle["meta"]["demo_mode"] is False
    assert bundle["meta"]["disclaimer_text"] == ""
    assert bundle["provenance"]["bundle_builder_version"] == "0.2.0-m2"
    assert bundle["meta"]["freshness"] == "current"
    assert set(bundle["provenance"]["agent_delta_tables"]) == set(AGENTS_PRESENT_KEYS)
    mock_validate.assert_called_once()
    mock_write.assert_called_once()


def test_bundle_builder_halts_when_validate_fails() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()

    with (
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value={},
        ),
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value={},
        ),
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        ),
        patch(
            "agents.orchestrator.bundle_builder.validate_bundle",
            side_effect=BundleValidationError("schema fail"),
        ),
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        ) as mock_write,
    ):
        with pytest.raises(BundleValidationError):
            builder.build("Elder Care", "uc13_ale", spark=mock_spark)

    mock_write.assert_not_called()


def test_bundle_builder_raises_without_spark() -> None:
    builder = BundleBuilder()
    mock_sql = MagicMock()
    mock_sql.SparkSession.getActiveSession.return_value = None
    with patch.dict("sys.modules", {"pyspark": MagicMock(), "pyspark.sql": mock_sql}):
        with pytest.raises(RuntimeError, match="No active Spark session"):
            builder.build("Elder Care", "uc13_ale", spark=None)


def test_bundle_builder_skips_synthesis_when_llm_endpoint_none() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    with ExitStack() as stack:
        _enter_build_patches(stack)
        mock_call_llm = stack.enter_context(
            patch("agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm")
        )
        stack.enter_context(
            patch("agents.orchestrator.bundle_builder.validate_bundle")
        )
        builder.build("Elder Care", "uc13_ale", spark=mock_spark, llm_endpoint=None)

    mock_call_llm.assert_not_called()


def test_bundle_builder_skips_synthesis_when_llm_endpoint_empty() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    with ExitStack() as stack:
        _enter_build_patches(stack)
        mock_call_llm = stack.enter_context(
            patch("agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm")
        )
        stack.enter_context(
            patch("agents.orchestrator.bundle_builder.validate_bundle")
        )
        builder.build("Elder Care", "uc13_ale", spark=mock_spark, llm_endpoint="")

    mock_call_llm.assert_not_called()


def test_bundle_builder_synthesis_populates_executive_preserves_risks() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    snapshots = _load_elder_care_snapshots()
    llm_payload = {
        "executive": {
            "in_one_line": "Regional elder care platform with stable census trends.",
            "preliminary_view": {
                "strengths": ["Diversified payer mix", "Strong branch footprint"],
                "concerns": ["Founder concentration", "Missing cost reports"],
                "closing": "Further diligence required before forming a view.",
            },
        },
        "risks": [{"risk": "LLM must not write this", "severity": "critical"}],
        "headline_metrics": {"ltm_revenue": "LLM override"},
    }

    with ExitStack() as stack:
        _enter_build_patches(stack, snapshots)
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
                return_value='{"executive": {}}',
            )
        )
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
                return_value=llm_payload,
            )
        )
        bundle = builder.build(
            "Elder Care",
            "uc13_ale",
            spark=mock_spark,
            llm_endpoint="databricks-claude-sonnet-4-6",
        )

    assert bundle["executive"]["in_one_line"] == llm_payload["executive"]["in_one_line"]
    assert bundle["executive"]["preliminary_view"]["strengths"]
    risks_without_synth = _risks_without_llm_endpoint(snapshots)
    assert bundle["risks"] == risks_without_synth
    validate_bundle(bundle)


def test_bundle_builder_synthesis_fail_open_on_llm_parse_error() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    snapshots = _load_elder_care_snapshots()

    with ExitStack() as stack:
        _enter_build_patches(stack, snapshots)
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
                return_value="not json",
            )
        )
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
                side_effect=ValueError("invalid JSON"),
            )
        )
        bundle = builder.build(
            "Elder Care",
            "uc13_ale",
            spark=mock_spark,
            llm_endpoint="databricks-claude-sonnet-4-6",
        )

    assert not str(bundle["executive"].get("in_one_line") or "").strip()
    validate_bundle(bundle)


def _risks_without_llm_endpoint(snapshots: dict) -> list:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    with ExitStack() as stack:
        _enter_build_patches(stack, snapshots)
        mock_call = stack.enter_context(
            patch("agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm")
        )
        bundle = builder.build("Elder Care", "uc13_ale", spark=mock_spark, llm_endpoint=None)
    mock_call.assert_not_called()
    return deepcopy(bundle["risks"])


def test_synthesize_executive_narrative_uses_snapshots_not_rendered_md() -> None:
    """Falsifier: stage 6 input must not use full_report.md; feeds assembled bundle sections."""
    bundle = {
        "meta": {"company_name": "Elder Care"},
        "executive": {
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
        },
        "risks": [{"risk": "keep", "severity": "track"}],
        "headline_metrics": {"ltm_revenue": "18M"},
        "legal": {},
        "data_room_gaps": [],
        "kpi_dashboard": [],
        "diligence_questions": [],
        "company_framing": {},
    }
    snapshots = {"business_model": {"delta_row": {}, "yaml_dict": {"executive_summary": "Co"}}}
    captured_prompt: list[str] = []

    def _capture_call(_system, user_prompt, _endpoint, **kwargs):
        captured_prompt.append(user_prompt)
        return "{}"

    with (
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
            side_effect=_capture_call,
        ),
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
            return_value={
                "executive": {"in_one_line": "From snapshots", "preliminary_view": {}},
            },
        ),
    ):
        synthesize_executive_narrative(
            bundle,
            snapshots,
            "databricks-claude-sonnet-4-6",
        )

    assert captured_prompt
    payload = json.loads(captured_prompt[0])
    assert "assembled_bundle_sections" in payload
    assert "agent_snapshots" not in payload
    assert "full_report" not in captured_prompt[0]
    assert bundle["executive"]["in_one_line"] == "From snapshots"
    assert bundle["risks"] == [{"risk": "keep", "severity": "track"}]


def test_executive_llm_system_prompt_r3_analysis_notes_and_dropped_mitigants() -> None:
    """Falsifier: Rev3 drops mitigants_digest prompt instruction; Analysis Notes is prose-only."""
    assert "mitigants_digest" not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "headline + why/relationship" not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "Risk Mitigation" not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "single small paragraph" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "tighter bulleted" not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "prose only, no bullets" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "gap_context" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "mitigation-strategy" not in _EXECUTIVE_LLM_SYSTEM_PROMPT


def test_executive_llm_system_prompt_v1_2_digest_expansion() -> None:
    """Falsifier: v1.3.0 keeps preliminary_digest only; four per-section digests retired from prompt."""
    assert "preliminary_digest" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    for dropped in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert dropped not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "Analysis Notes" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "risk dimension" not in _EXECUTIVE_LLM_SYSTEM_PROMPT


def test_executive_synthesis_gap_context_includes_bundle_gap_signals() -> None:
    bundle = {
        "data_room_gaps": [{"item": "Missing QoE", "priority": "high", "fill_state": "filled_cited"}],
        "confidence_by_area": {"financial_trends": "medium", "legal": "low"},
        "risks": [
            {
                "risk": "Concentration",
                "severity": "material",
                "fill_state": "filled_synthesized",
                "mitigant_or_question": "Diversify",
            }
        ],
        "kpi_dashboard": [
            {"metric_id": "nrr", "fill_state": "gap_correct", "flag": "N/A"},
            {"metric_id": "ltm_rev", "fill_state": "filled_cited", "flag": "Green"},
        ],
        "executive": {"in_one_line": ""},
    }
    ctx = _executive_synthesis_gap_context(bundle)
    assert ctx["data_room_gaps"][0]["item"] == "Missing QoE"
    assert ctx["confidence_by_area"]["legal"] == "low"
    assert isinstance(ctx["synthesis_gaps"], list)
    assert ctx["risks"][0]["risk"] == "Concentration"
    assert ctx["kpi_gaps"][0]["metric_id"] == "nrr"


def test_synthesize_executive_narrative_includes_gap_context_in_user_prompt() -> None:
    """Falsifier: stage-6 user JSON must carry gap_context for confidence grounding."""
    bundle = {
        "meta": {"company_name": "Elder Care"},
        "executive": _executive_shell(),
        "data_room_gaps": [{"item": "No cap table", "priority": "medium", "fill_state": "filled_cited"}],
        "confidence_by_area": {"business_model": "high"},
        "risks": [],
        "kpi_dashboard": [],
    }
    snapshots = {"business_model": {"delta_row": {}, "yaml_dict": {}}}
    captured: list[str] = []

    with (
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
            side_effect=lambda _s, user, _e, **kw: captured.append(user) or "{}",
        ),
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
            return_value={"executive": {"in_one_line": "ok"}},
        ),
    ):
        synthesize_executive_narrative(bundle, snapshots, "databricks-claude-sonnet-4-6")

    assert captured
    payload = json.loads(captured[0])
    assert "gap_context" in payload
    assert payload["gap_context"]["data_room_gaps"][0]["item"] == "No cap table"
    assert payload["gap_context"]["confidence_by_area"]["business_model"] == "high"


def _executive_shell() -> dict:
    return {
        "in_one_line": "",
        "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
    }


def test_merge_executive_llm_narrative_admits_expanded_narrative_fields() -> None:
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "business_snapshot_narrative": "  Regional platform with stable census. ",
            "mitigants_digest": "Management has diversified payer mix.",
            "confidence_rationale": "Financial trends are well supported.",
            "in_one_line": "Synthesized headline.",
            "preliminary_view": {"strengths": ["A"], "concerns": [], "closing": "Review."},
        }
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["business_snapshot_narrative"] == "Regional platform with stable census."
    assert bundle["executive"]["mitigants_digest"] == "Management has diversified payer mix."
    assert bundle["executive"]["confidence_rationale"] == "Financial trends are well supported."
    assert bundle["executive"]["in_one_line"] == "Synthesized headline."


def test_merge_executive_llm_narrative_admits_v1_2_digest_fields() -> None:
    """§2Δ.3: preliminary_digest merges; four per-section digests are no longer admitted."""
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "legal_digest": "  Seven of eleven contracts assessed with high confidence. ",
            "qoe_digest": "Adjusted EBITDA holds after addbacks.",
            "kpi_digest": "Census and payer mix metrics are green.",
            "open_items_digest": "Cap table and insurance schedules remain open.",
            "preliminary_digest": "Attractive regional platform with manageable risks.",
        }
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["preliminary_digest"] == "Attractive regional platform with manageable risks."
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in bundle["executive"]


def test_executive_llm_narrative_keys_allowlist_includes_v1_2_digests() -> None:
    """Falsifier: prompt+allowlist co-move — preliminary_digest in; four section digests out."""
    assert "preliminary_digest" in _EXECUTIVE_LLM_NARRATIVE_KEYS
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in _EXECUTIVE_LLM_NARRATIVE_KEYS


def test_merge_executive_llm_narrative_drops_unknown_executive_keys() -> None:
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "business_snapshot_narrative": "Keep me.",
            "risks": [{"risk": "drop me"}],
            "headline_metrics": {"ltm_revenue": "drop me"},
        },
        "headline_metrics": {"ltm_revenue": "top-level drop"},
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["business_snapshot_narrative"] == "Keep me."
    assert "risks" not in bundle
    assert "headline_metrics" not in bundle


def test_bundle_builder_synthesis_populates_expanded_executive_narrative_fields() -> None:
    """§2.5: Stage 6 synthesis wires optional executive narrative keys end-to-end."""
    builder = BundleBuilder()
    mock_spark = MagicMock()
    snapshots = _load_elder_care_snapshots()
    llm_payload = {
        "executive": {
            "business_snapshot_narrative": "  Rich regional elder care platform. ",
            "mitigants_digest": "Payer mix diversification limits concentration risk.",
            "confidence_rationale": "Financial trends are well supported in the CIM.",
            "in_one_line": "Regional elder care platform with stable census.",
            "preliminary_view": {
                "strengths": ["Diversified payer mix"],
                "concerns": [],
                "closing": "Further diligence required.",
            },
        },
    }

    with ExitStack() as stack:
        _enter_build_patches(stack, snapshots)
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
                return_value='{"executive": {}}',
            )
        )
        stack.enter_context(
            patch(
                "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
                return_value=llm_payload,
            )
        )
        bundle = builder.build(
            "Elder Care",
            "uc13_ale",
            spark=mock_spark,
            llm_endpoint="databricks-claude-sonnet-4-6",
        )

    assert bundle["executive"]["business_snapshot_narrative"] == "Rich regional elder care platform."
    assert bundle["executive"]["mitigants_digest"] == (
        "Payer mix diversification limits concentration risk."
    )
    assert bundle["executive"]["confidence_rationale"] == (
        "Financial trends are well supported in the CIM."
    )
    validate_bundle(bundle)


def test_executive_synthesis_bundle_context_includes_assembled_sections() -> None:
    """§2Δ.1: stage-6 input carries bounded assembled bundle sections, not raw reports."""
    bundle = {
        "company_framing": {"business_model": "Regional elder care"},
        "financials": {"ltm_revenue": "18M"},
        "revenue_quality": {"concentration": "low"},
        "kpi_dashboard": [{"metric_id": "nrr"}],
        "legal": {"assessed": 7, "total": 11},
        "qoe": {"adjusted_ebitda": "4.2M"},
        "risks": [{"risk": "Concentration", "severity": "material"}],
        "confidence_by_area": {"financial_trends": "high"},
        "headline_metrics": {"ltm_revenue": "18M"},
        "data_room_gaps": [{"item": "Cap table"}],
    }
    ctx = _executive_synthesis_bundle_context(bundle)
    assert set(ctx) == set(_EXECUTIVE_SYNTHESIS_BUNDLE_SECTION_KEYS)
    assert ctx["company_framing"]["business_model"] == "Regional elder care"
    assert ctx["legal"]["assessed"] == 7
    assert ctx["risks"][0]["risk"] == "Concentration"


def test_synthesize_executive_narrative_uses_assembled_bundle_sections() -> None:
    """Falsifier: stage-6 user JSON feeds assembled sections, not agent snapshots or full_report."""
    bundle = {
        "meta": {"company_name": "Elder Care"},
        "executive": {
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
        },
        "company_framing": {"business_model": "Regional elder care"},
        "financials": {"ltm_revenue": "18M"},
        "revenue_quality": {},
        "kpi_dashboard": [],
        "legal": {},
        "qoe": {},
        "risks": [{"risk": "keep", "severity": "track"}],
        "confidence_by_area": {},
        "headline_metrics": {"ltm_revenue": "18M"},
        "data_room_gaps": [],
        "diligence_questions": [],
    }
    snapshots = {"business_model": {"delta_row": {}, "yaml_dict": {"executive_summary": "Co"}}}
    captured_prompt: list[str] = []

    def _capture_call(_system, user_prompt, _endpoint, **kwargs):
        captured_prompt.append(user_prompt)
        return "{}"

    with (
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._call_llm",
            side_effect=_capture_call,
        ),
        patch(
            "agents.orchestrator.bundle_builder._OrchestratorLlm._parse_json_response",
            return_value={
                "executive": {"in_one_line": "From bundle", "preliminary_view": {}},
            },
        ),
    ):
        synthesize_executive_narrative(
            bundle,
            snapshots,
            "databricks-claude-sonnet-4-6",
        )

    assert captured_prompt
    payload = json.loads(captured_prompt[0])
    assert "assembled_bundle_sections" in payload
    assert payload["assembled_bundle_sections"]["financials"]["ltm_revenue"] == "18M"
    assert "agent_snapshots" not in payload
    assert "full_report" not in captured_prompt[0]
    assert bundle["executive"]["in_one_line"] == "From bundle"
    assert bundle["risks"] == [{"risk": "keep", "severity": "track"}]


def test_executive_llm_system_prompt_v1_3_consolidated_overview() -> None:
    """Falsifier: v1.3.0 reframes preliminary_digest; drops four section digests."""
    for tag in _PRELIMINARY_DIGEST_SECTION_TAGS:
        assert tag in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "assembled_bundle_sections" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "NOT a restatement" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    for dropped in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert dropped not in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "preliminary_digest" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "risk dimension" not in _EXECUTIVE_LLM_SYSTEM_PROMPT


def test_executive_llm_system_prompt_r3_business_snapshot_closing_and_thesis() -> None:
    """Falsifier: Rev3 concise Business Snapshot, load-bearing thesis cap, and company-focused closing."""
    assert "warrants a deeper dive" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "3–5 sentences max" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "4–6 short bullets maximum" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "load-bearing themes" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "omit marginal themes" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "single most consequential open question" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "not a checklist of generic diligence" in _EXECUTIVE_LLM_SYSTEM_PROMPT


def test_merge_executive_llm_narrative_drops_v1_2_section_digests() -> None:
    """§2Δ.3: four per-section digests are no longer admitted via the allowlist."""
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "legal_digest": "Should not merge.",
            "qoe_digest": "Should not merge.",
            "kpi_digest": "Should not merge.",
            "open_items_digest": "Should not merge.",
            "preliminary_digest": "Cross-bundle overview. [Financial Strip]",
        }
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["preliminary_digest"] == "Cross-bundle overview. [Financial Strip]"
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in bundle["executive"]


def test_executive_llm_narrative_keys_allowlist_excludes_dropped_digests() -> None:
    """Falsifier: prompt+allowlist co-move — dropped digest keys must not be in the frozenset."""
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in _EXECUTIVE_LLM_NARRATIVE_KEYS
    assert "preliminary_digest" in _EXECUTIVE_LLM_NARRATIVE_KEYS


def test_executive_llm_narrative_keys_allowlist_includes_thesis_and_watchouts() -> None:
    """T4: allowlist admits the two new executive string[] synthesis fields."""
    assert "thesis_bullets" in _EXECUTIVE_LLM_NARRATIVE_KEYS
    assert "key_watchouts" in _EXECUTIVE_LLM_NARRATIVE_KEYS


def test_executive_llm_narrative_keys_do_not_collide_with_structural_sections() -> None:
    """T4 kill criterion: new keys must not be silently discarded by restore-after-LLM."""
    preserved_keys = {
        "meta",
        "legal",
        "data_room_gaps",
        "kpi_dashboard",
        "risks",
        "diligence_questions",
        "headline_metrics",
        "company_framing",
    }
    new_keys = {"thesis_bullets", "key_watchouts"}
    assert not new_keys & set(_EXECUTIVE_SYNTHESIS_BUNDLE_SECTION_KEYS)
    assert not new_keys & preserved_keys


def test_merge_executive_llm_narrative_admits_thesis_and_watchouts() -> None:
    """T4: merge writes thesis_bullets and key_watchouts from mocked LLM string[] output."""
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "thesis_bullets": [
                "  Regional platform with offshore staffing. ",
                "Acquisition-led growth.",
            ],
            "key_watchouts": [
                "Caregiver recruiting in tight labor markets",
                "Referral concentration",
            ],
        }
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["thesis_bullets"] == [
        "Regional platform with offshore staffing.",
        "Acquisition-led growth.",
    ]
    assert bundle["executive"]["key_watchouts"] == [
        "Caregiver recruiting in tight labor markets",
        "Referral concentration",
    ]


def test_merge_executive_llm_narrative_leaves_thesis_watchouts_untouched_when_absent_or_empty() -> None:
    """T4: absent/empty thesis_bullets and key_watchouts do not overwrite bundle executive."""
    bundle = {"executive": _executive_shell()}
    _merge_executive_llm_narrative(
        bundle,
        {"executive": {"thesis_bullets": [], "key_watchouts": None}},
    )
    assert "thesis_bullets" not in bundle["executive"]
    assert "key_watchouts" not in bundle["executive"]


def test_merge_executive_llm_narrative_filters_non_string_thesis_watchout_items() -> None:
    """Falsifier: non-string list items are dropped by _string_list, not coerced."""
    bundle = {"executive": _executive_shell()}
    llm_result = {
        "executive": {
            "thesis_bullets": ["Keep me", 42, "", "  Also keep  "],
            "key_watchouts": [None, "Valid watchout"],
        }
    }
    _merge_executive_llm_narrative(bundle, llm_result)
    assert bundle["executive"]["thesis_bullets"] == ["Keep me", "Also keep"]
    assert bundle["executive"]["key_watchouts"] == ["Valid watchout"]


def test_executive_llm_system_prompt_bucket_b_attribution_instruction() -> None:
    """T4: Bucket B attribution/qualification instruction is present in the Stage 6 prompt."""
    assert "qualify it with source and period" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "do not silently pick one canonical number" in _EXECUTIVE_LLM_SYSTEM_PROMPT


def test_executive_llm_system_prompt_omits_wage_inflation_theme() -> None:
    """T4: key_watchouts prompt explicitly omits wage-inflation-vs-pricing (no data source)."""
    assert "wage-inflation-vs-pricing" in _EXECUTIVE_LLM_SYSTEM_PROMPT
    assert "omit this theme" in _EXECUTIVE_LLM_SYSTEM_PROMPT

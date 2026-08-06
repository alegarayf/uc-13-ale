"""Unit tests for agents.exec_summary.rainmaker_narrative — Capa B synthesis.

Paso 3 (digest builder, no LLM) + Paso 4 (bounded LLM calls, mocked) of
docs/plans/plan_raimaker_format.md. No company-specific literals in bundle
fixtures — periods/labels are generic so this generalizes across verticals
(plan §Principios rectores, P2).
"""

from __future__ import annotations

import json

import pytest

from agents.exec_summary.rainmaker_narrative import (
    _build_narrative_digest,
    synthesize_rainmaker_narrative,
)


def _bundle(**overrides) -> dict:
    base = {
        "meta": {"vertical_overlay": "b2b_saas", "company_name": "Acme"},
        "executive": {"in_one_line": "A thing that does a thing.", "thesis_bullets": ["Bullet A", "Bullet B"]},
        "company_framing": {
            "overview_bullets": ["Founded 2020", "Remote team"],
            "revenue_model": {"tag": "subscription", "quality_flag": "durable", "note": "Recurring."},
        },
        "revenue_quality": {
            "scale_narrative": "Scale narrative.",
            "concentration": "Top 10 = 40%.",
            "end_market_mix": "SaaS 80%, other 20%.",
            "retention_notes": "NRR 110%.",
        },
        "kpi_dashboard": [{"display_name": "ARR", "stated_value": "$5M"}],
        "risks": [{"risk": "concentration", "severity": "material", "evidence": "Doc p.1", "mitigant_or_question": "Ask about top accounts"}],
        "data_room_gaps": [{"item": "Missing signed contracts"}],
        "financials": {"table_rows": [{"year": "2024A", "revenue": "$5.0", "ebitda": "$1.0", "gross_margin_pct": "80%", "ebitda_margin_pct": "20%"}]},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Paso 3 — _build_narrative_digest
# ---------------------------------------------------------------------------


def test_digest_never_leaks_forbidden_bundle_sections():
    contaminated = _bundle(
        chunks=["raw chunk text"],
        embeddings=[[0.1, 0.2]],
        reasoning_trace=["step 1", "step 2"],
        citations=[{"doc": "x.pdf", "page": 1}],
    )
    digest = _build_narrative_digest(contaminated)
    serialized = json.dumps(digest)
    for forbidden in ("raw chunk text", "reasoning_trace", "embeddings", "0.1, 0.2"):
        assert forbidden not in serialized


def test_digest_includes_revenue_model_for_diligence_relevance_f3():
    digest = _build_narrative_digest(_bundle())
    assert digest["revenue_model"]["tag"] == "subscription"
    assert digest["revenue_quality"]["concentration"] == "Top 10 = 40%."


def test_digest_empty_bundle_never_sends_fabricated_content():
    digest = _build_narrative_digest({})
    assert digest["in_one_line"] == ""
    assert digest["thesis_bullets"] == []
    assert digest["overview_bullets"] == []
    assert digest["kpi_highlights"] == []
    assert digest["risks"] == []
    assert digest["data_room_gaps"] == []


def test_digest_financials_summary_uses_capa_a_table_not_raw_rows():
    from agents.exec_summary.rainmaker_view import rainmaker_view

    bundle = _bundle()
    view = rainmaker_view(bundle)
    digest = _build_narrative_digest(bundle, view["financials"])
    assert digest["financials_summary"]["latest_revenue"] == "$5.0"
    assert digest["financials_summary"]["latest_ebitda"] == "$1.0"
    assert "table_rows" not in digest


def test_digest_caps_are_respected():
    many_risks = [
        {"risk": f"risk-{i}", "severity": "track", "evidence": "", "mitigant_or_question": ""}
        for i in range(20)
    ]
    digest = _build_narrative_digest(_bundle(risks=many_risks))
    assert len(digest["risks"]) <= 8


# ---------------------------------------------------------------------------
# Paso 4 — synthesize_rainmaker_narrative (LLM mocked)
# ---------------------------------------------------------------------------


_VALID_FRAMING_RESPONSE = json.dumps(
    {
        "one_liner": "A durable subscription business with expanding accounts.",
        "company_overview": ["Founded 2020", "Remote team"],
        "business_model": ["Subscription, recurring revenue"],
        "investment_thesis": {"value_drivers": ["Strong NRR", "Low concentration"], "why_special": "Durable recurring revenue."},
        "recommendation": "Worthy of additional pursuit because of A, B and C, subject primarily to proving X, Y and Z.",
    }
)
_VALID_REVQUAL_RESPONSE = json.dumps(
    {
        "commercial_revenue_quality": [{"topic": "Concentration", "detail": "Top 10 = 40%."}],
        "diligence_priorities": ["Validate NRR calculation methodology"],
    }
)


class _StubLlm:
    """Stands in for _RainmakerNarrativeLlm — records calls, returns canned text."""

    def __init__(self, responses, raise_on=None):
        self._responses = list(responses)
        self._raise_on = raise_on or set()
        self.calls = []

    def _call_llm(self, system_prompt, user_prompt, endpoint, max_tokens=12_000):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "max_tokens": max_tokens})
        call_index = len(self.calls) - 1
        if call_index in self._raise_on:
            raise TimeoutError("simulated timeout")
        return self._responses[call_index]

    def _parse_json_response(self, raw):
        return json.loads(raw)


def test_synthesize_success_when_both_calls_succeed(monkeypatch):
    stub = _StubLlm([_VALID_FRAMING_RESPONSE, _VALID_REVQUAL_RESPONSE])
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative._RainmakerNarrativeLlm", lambda: stub
    )
    result = synthesize_rainmaker_narrative(_bundle(), llm_endpoint="fake-endpoint")
    assert result["synthesis_status"] == "success"
    assert result["one_liner"]
    assert result["recommendation"]
    assert result["diligence_priorities"] == ["Validate NRR calculation methodology"]
    # both calls stayed within the bounded max_tokens budget (plan §3.2)
    assert all(c["max_tokens"] <= 4_000 for c in stub.calls)


def test_synthesize_degrades_on_exception_without_raising(monkeypatch):
    stub = _StubLlm([_VALID_FRAMING_RESPONSE, _VALID_REVQUAL_RESPONSE], raise_on={0, 1})
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative._RainmakerNarrativeLlm", lambda: stub
    )
    result = synthesize_rainmaker_narrative(_bundle(), llm_endpoint="fake-endpoint")
    assert result["synthesis_status"] == "degraded"
    assert result["one_liner"] is None
    assert result["diligence_priorities"] is None


def test_synthesize_degrades_on_invalid_json_without_raising(monkeypatch):
    stub = _StubLlm(["not valid json{{{", _VALID_REVQUAL_RESPONSE])
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative._RainmakerNarrativeLlm", lambda: stub
    )
    result = synthesize_rainmaker_narrative(_bundle(), llm_endpoint="fake-endpoint")
    assert result["synthesis_status"] in {"degraded", "partial"}
    assert result["one_liner"] is None


def test_synthesize_partial_when_only_one_call_succeeds(monkeypatch):
    stub = _StubLlm([_VALID_FRAMING_RESPONSE, _VALID_REVQUAL_RESPONSE], raise_on={1})
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative._RainmakerNarrativeLlm", lambda: stub
    )
    result = synthesize_rainmaker_narrative(_bundle(), llm_endpoint="fake-endpoint")
    assert result["synthesis_status"] == "partial"
    assert result["one_liner"]
    assert result["diligence_priorities"] is None


def test_synthesize_never_raises_even_if_llm_client_constructor_fails(monkeypatch):
    def _boom():
        raise RuntimeError("no endpoint configured")

    monkeypatch.setattr("agents.exec_summary.rainmaker_narrative._RainmakerNarrativeLlm", _boom)
    result = synthesize_rainmaker_narrative(_bundle(), llm_endpoint="fake-endpoint")
    assert result["synthesis_status"] == "degraded"

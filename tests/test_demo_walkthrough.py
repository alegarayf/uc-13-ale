"""Unit tests for orchestrator demo_walkthrough gates (M1 T8)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from agents.orchestrator import demo_walkthrough as dw


def _minimal_bundle() -> dict:
    return {
        "meta": {
            "demo_mode": True,
            "disclaimer_text": "Demo only — not investment advice.",
        },
        "confidence_by_area": {area: "medium" for area in dw.CONFIDENCE_AREAS},
        "risks": [
            {"risk": f"Risk {i}", "severity": "medium"} for i in range(1, 4)
        ],
        "diligence_questions": [
            {"category": "Legal", "question": f"Question {i}?"} for i in range(1, 3)
        ],
        "provenance": {
            "synthesis_gaps": [
                {
                    "field_path": "executive.thesis",
                    "reason": "not in agent snapshot",
                    "owner": "orchestrator",
                }
            ]
        },
    }


def _write_artifacts(vol_dir: Path, bundle: dict | None = None) -> None:
    vol_dir.mkdir(parents=True, exist_ok=True)
    data = bundle if bundle is not None else _minimal_bundle()
    (vol_dir / "orchestrator_bundle.yaml").write_text(
        yaml.dump(data, sort_keys=False), encoding="utf-8"
    )
    for name in dw.REQUIRED_ARTIFACTS:
        if name == "orchestrator_bundle.yaml":
            continue
        (vol_dir / name).write_text("stub", encoding="utf-8")


def test_run_passes_when_all_gates_satisfied(tmp_path, monkeypatch, capsys):
    company = "Elder Care"
    catalog = "uc13_ale"
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_artifacts(vol_dir)
    monkeypatch.setattr(dw, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = dw.run(company_name=company, catalog=catalog)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DEMO PASS" in out
    assert "Demo only" in out
    assert "business_model" in out
    assert "Risk 1" in out
    assert "Question 1?" in out
    assert "executive.thesis" in out


def test_run_fails_when_confidence_area_missing(tmp_path, monkeypatch, capsys):
    company = "Elder Care"
    catalog = "uc13_ale"
    vol_dir = tmp_path / "reports" / "Elder_Care"
    bundle = _minimal_bundle()
    del bundle["confidence_by_area"]["legal"]
    _write_artifacts(vol_dir, bundle)
    monkeypatch.setattr(dw, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = dw.run(company_name=company, catalog=catalog)

    assert exit_code == 1
    assert "[orchestrator] DEMO FAIL: confidence_by_area.legal missing" in capsys.readouterr().out


def test_run_fails_when_docx_artifact_missing(tmp_path, monkeypatch, capsys):
    """Falsifier: gate 7 must reject missing DOCX even when bundle YAML is valid."""
    company = "Elder Care"
    catalog = "uc13_ale"
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_artifacts(vol_dir)
    os.remove(vol_dir / "full_report.docx")
    monkeypatch.setattr(dw, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = dw.run(company_name=company, catalog=catalog)

    assert exit_code == 1
    assert "full_report.docx" in capsys.readouterr().out


def test_format_diligence_question_parses_legacy_dict_repr():
    row = {
        "category": "legal",
        "question": "{'doc_type': 'Healthcare Referral Agreements', 'item_id': 'healthcare_referral'}",
    }
    assert dw._format_diligence_question(row) == (
        "Request and review Healthcare Referral Agreements"
    )


def test_reports_volume_dir_uses_company_safe():
    from agents.orchestrator.paths import reports_volume_dir

    path = reports_volume_dir("uc13_ale", "Elder Care")
    assert path.endswith("/Elder_Care")
    assert " " not in path.split("/")[-1]

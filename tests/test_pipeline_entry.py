"""Unit tests for agents.exec_summary.pipeline_entry.build_exec_summary (T9)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.exec_summary.pipeline_entry import build_exec_summary


def test_build_exec_summary_wires_stages_in_order_and_returns_all_paths() -> None:
    """build → validate → render → convert (both .md files) in that order."""
    calls: list[str] = []

    fake_bundle = {"meta": {"company_name": "Elder Care"}}

    fake_build_instance = MagicMock()
    fake_build_instance.build.side_effect = lambda *a, **k: (
        calls.append("build") or fake_bundle
    )
    fake_builder_cls = MagicMock(return_value=fake_build_instance)

    def fake_validate(bundle):
        calls.append("validate")
        assert bundle is fake_bundle

    def fake_render(bundle, catalog, company_name):
        calls.append("render")
        return {
            "full_report": "/Volumes/uc13/analysis/reports/Elder_Care/full_report.md",
            "tldr": "/Volumes/uc13/analysis/reports/Elder_Care/tldr_one_pager.md",
        }

    def fake_convert(md_path, out_path):
        calls.append(f"convert:{md_path}")
        return out_path

    with (
        patch("agents.exec_summary.pipeline_entry.BundleBuilder", fake_builder_cls),
        patch("agents.exec_summary.pipeline_entry.validate_bundle", fake_validate),
        patch("agents.exec_summary.pipeline_entry.render_to_volume", fake_render),
        patch(
            "agents.exec_summary.pipeline_entry._load_convert_md_to_word",
            return_value=fake_convert,
        ),
    ):
        result = build_exec_summary(
            company_name="Elder Care",
            catalog="uc13",
            spark=MagicMock(),
            llm_endpoint="databricks-claude-sonnet-4-6",
        )

    # Stage order is load-bearing: render reads validated bundle; convert reads rendered .md.
    assert calls == [
        "build",
        "validate",
        "render",
        "convert:/Volumes/uc13/analysis/reports/Elder_Care/full_report.md",
        "convert:/Volumes/uc13/analysis/reports/Elder_Care/tldr_one_pager.md",
    ]

    assert result == {
        "full_report_md": "/Volumes/uc13/analysis/reports/Elder_Care/full_report.md",
        "tldr_md": "/Volumes/uc13/analysis/reports/Elder_Care/tldr_one_pager.md",
        "full_report_docx": "/Volumes/uc13/analysis/reports/Elder_Care/full_report.docx",
        "tldr_docx": "/Volumes/uc13/analysis/reports/Elder_Care/tldr_one_pager.docx",
    }

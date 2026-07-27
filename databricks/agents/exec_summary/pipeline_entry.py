"""UC13 exec_summary ↔ DAG bridge (T9).

Wires the Rainmaker-Rev3 executive one-pager (mine, ``agents.exec_summary``)
into Hector's DAG entry points (``run_full_pipeline.py`` / ``run_vdr_pipeline.py``)
so the e2e run emits both the full diligence memo and the one-pager.

Must be called AFTER Hector's DAG (``agents.orchestration.pipeline.run_pipeline``)
has completed for ``company_name`` — the ingest step reads per-agent
``*_report.yaml`` snapshots + ``{catalog}.analysis.*`` Delta rows that only exist
once the DAG's agents have run.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from agents.exec_summary.bundle_builder import BundleBuilder
from agents.exec_summary.validate import validate_bundle
from agents.exec_summary.renderers import render_to_volume

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def _load_convert_md_to_word():
    """Import convert_md_to_word robustly across notebook / module contexts."""
    try:
        from jobs.scripts.md_to_word import convert_md_to_word
        return convert_md_to_word
    except Exception:
        pass
    try:
        import md_to_word  # SCRIPTS dir on sys.path (notebook convention)
        return md_to_word.convert_md_to_word
    except Exception:
        here = os.path.dirname(os.path.abspath(__file__))
        root = here
        for _ in range(5):
            if os.path.isdir(os.path.join(root, "jobs", "scripts")):
                break
            root = os.path.dirname(root)
        sp = os.path.join(root, "jobs", "scripts")
        if sp not in sys.path:
            sys.path.insert(0, sp)
        import md_to_word
        return md_to_word.convert_md_to_word


def build_exec_summary(
    company_name: str,
    catalog: str,
    spark: "SparkSession",
    llm_endpoint: str | None,
) -> dict[str, str]:
    """Build the Rev3 executive one-pager + full report from a completed DAG run.

    Wraps, in order: ``BundleBuilder().build`` → ``validate_bundle`` →
    ``render_to_volume`` → ``convert_md_to_word`` (on both rendered .md files).

    Returns a dict of output paths: ``tldr_md``, ``full_report_md``,
    ``tldr_docx``, ``full_report_docx``.
    """
    bundle = BundleBuilder().build(company_name, catalog, spark, llm_endpoint)
    validate_bundle(bundle)
    rendered = render_to_volume(bundle, catalog, company_name)

    paths: dict[str, str] = {
        "full_report_md": rendered["full_report"],
        "tldr_md": rendered["tldr"],
    }

    convert_md_to_word = _load_convert_md_to_word()
    for md_key, docx_key in (
        ("full_report_md", "full_report_docx"),
        ("tldr_md", "tldr_docx"),
    ):
        md_path = paths[md_key]
        base, _ = os.path.splitext(md_path)
        docx_path = f"{base}.docx"
        paths[docx_key] = convert_md_to_word(md_path, docx_path)

    return paths

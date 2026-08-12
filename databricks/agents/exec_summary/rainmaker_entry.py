"""Rainmaker executive-review bridge — the sibling of ``pipeline_entry.py``.

Wires the Rainmaker-format executive review (``rainmaker_view`` +
``rainmaker_narrative`` + ``renderers.render_rainmaker``) into any caller that
has already run the 7 workstream agents for ``company_name`` — the CIM-scoped
preview and the full-room flow both call this same function so the executive
review is produced through one code path regardless of which one ran.

Must be called AFTER the agent DAG (``agents.orchestration.pipeline.run_pipeline``
or the CIM-scoped equivalent) has completed for ``company_name`` — ``BundleBuilder``
reads per-agent ``{catalog}.analysis.*`` Delta rows that only exist once the
agents have run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def build_rainmaker_summary(
    company_name: str,
    catalog: str,
    spark: "SparkSession",
    llm_endpoint: str,
) -> dict[str, Any]:
    """Build the Rainmaker-format executive review from a completed agent run.

    Wraps, in order: ``BundleBuilder().build`` → ``validate_bundle`` →
    ``verify_bundle_claims`` → ``synthesize_rainmaker_narrative`` →
    ``render_rainmaker``.

    ``verify_bundle_claims`` (plan Part B, B2) runs between validation and
    narrative synthesis: it checks a small set of narrative-feeding fields
    that read as empty against the actual data room, and reclassifies a
    false "nothing here" into "present but not extracted" before the
    narrative LLM ever sees it — so both VDR branches get the fix for free.

    Catalog-agnostic on purpose: the CIM preview passes ``uc13_preview``, and
    the full-room flow also passes ``uc13_preview`` (both VDR modes share one
    working catalog — see the plan's §3). Returns ``{"html": path,
    "pdf": path?, "synthesis_status": str}``. ``pdf`` is present only when a
    PDF engine succeeded (``render_rainmaker``'s own contract).
    """
    from agents.exec_summary.absence_check import verify_bundle_claims
    from agents.exec_summary.bundle_builder import BundleBuilder
    from agents.exec_summary.rainmaker_narrative import synthesize_rainmaker_narrative
    from agents.exec_summary.renderers import render_rainmaker
    from agents.exec_summary.validate import validate_bundle

    bundle = BundleBuilder().build(company_name, catalog, spark, llm_endpoint)
    validate_bundle(bundle)

    checked_bundle = verify_bundle_claims(bundle, spark, catalog, company_name)

    narrative = synthesize_rainmaker_narrative(checked_bundle, llm_endpoint, spark)
    print(f"  Rainmaker narrative synthesis: {narrative.get('synthesis_status')}")

    rendered = render_rainmaker(checked_bundle, catalog, company_name, narrative=narrative)

    return {**rendered, "synthesis_status": narrative.get("synthesis_status")}

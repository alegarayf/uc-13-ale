"""
vs_filter_pushdown_probe.py — M-RE3 entry gate (charter items 24–25).

Probes Databricks Vector Search ``filters_json`` pushdown for:
  - ``company_name`` (re-verify G2 / D6)
  - ``workstream`` (ARRAY<STRING> — array-overlap / multi-value candidates)
  - ``priority_tier`` (INT — equality and comparison operators)

Calls ``WorkspaceClient().vector_search_indexes.query_index()`` directly so
malformed predicates surface as SDK errors instead of silently degrading via
``retrieval._query_vector_index``'s unfiltered fallback.

Operator-facing pass/fail matrix: ``eval/retrieval/README.md`` § M-RE3 VS filter
pushdown spike.

Typical usage (Databricks notebook cell, after Cell 1 config):

    import importlib
    import vs_filter_pushdown_probe as probe
    importlib.reload(probe)

    result = probe.main(spark, catalog="uc13_ale", company_name="Elder Care")
    print(result)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Repo / param helpers (notebook + job convention)
# ---------------------------------------------------------------------------


def _get_dbutils():
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython

        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def _load_dotenv_if_local():
    if _get_dbutils() is None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass


_load_dotenv_if_local()


def get_param(key: str, default: str | None = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a job task parameter. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


def get_current_path() -> Path:
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker: str = "agents") -> str:
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


# ---------------------------------------------------------------------------
# Probe candidates (Databricks VS standard-endpoint filter dict DSL)
# ---------------------------------------------------------------------------

ProbeStatus = Literal["pass", "fail", "pending"]
Dimension = Literal["company_name", "workstream", "priority_tier"]


@dataclass(frozen=True)
class FilterCandidate:
    """One row in the README pass/fail matrix."""

    dimension: Dimension
    label: str
    filters: dict[str, Any]
    notes: str


def _workstream_candidates() -> list[FilterCandidate]:
    """Array-overlap / multi-value candidates for ARRAY<STRING> workstream."""
    return [
        FilterCandidate(
            dimension="workstream",
            label='equality scalar {"workstream": "FINANCIAL"}',
            filters={"workstream": "FINANCIAL"},
            notes=(
                "Exact-match operator (no suffix). May match whole-array equality "
                "only — not documented as array-overlap."
            ),
        ),
        FilterCandidate(
            dimension="workstream",
            label='list any-of {"workstream": ["FINANCIAL"]}',
            filters={"workstream": ["FINANCIAL"]},
            notes="Multi-value equality per VS filter guide (matches any listed value).",
        ),
        FilterCandidate(
            dimension="workstream",
            label='list any-of {"workstream": ["FINANCIAL", "BUSINESS_MODEL"]}',
            filters={"workstream": ["FINANCIAL", "BUSINESS_MODEL"]},
            notes="Overlap proxy: any-of on index array column (not documented as ARRAY_CONTAINS).",
        ),
        FilterCandidate(
            dimension="workstream",
            label='LIKE {"workstream LIKE": "FINANCIAL"}',
            filters={"workstream LIKE": "FINANCIAL"},
            notes="Docs workaround for array overlap via string LIKE when arrays unsupported.",
        ),
    ]


def _priority_tier_candidates() -> list[FilterCandidate]:
    """Numeric equality / range candidates for INT priority_tier."""
    return [
        FilterCandidate(
            dimension="priority_tier",
            label='equality {"priority_tier": 2}',
            filters={"priority_tier": 2},
            notes="No operator suffix — exact match.",
        ),
        FilterCandidate(
            dimension="priority_tier",
            label='lte {"priority_tier <=": 2}',
            filters={"priority_tier <=": 2},
            notes="Operator-suffixed key per VS standard-endpoint filter dict.",
        ),
        FilterCandidate(
            dimension="priority_tier",
            label='gte {"priority_tier >=": 1}',
            filters={"priority_tier >=": 1},
            notes="Operator-suffixed key per VS standard-endpoint filter dict.",
        ),
        FilterCandidate(
            dimension="priority_tier",
            label='lt {"priority_tier <": 3}',
            filters={"priority_tier <": 3},
            notes="Strict less-than operator suffix.",
        ),
    ]


def _company_name_candidate(company_name: str) -> FilterCandidate:
    return FilterCandidate(
        dimension="company_name",
        label=f'equality {{"company_name": {company_name!r}}}',
        filters={"company_name": company_name},
        notes="G2 re-verify — same predicate shape as retrieval._query_vector_index.",
    )


def _combined_candidates(company_name: str) -> list[FilterCandidate]:
    return [
        FilterCandidate(
            dimension="workstream",
            label=(
                f'company + workstream '
                f'{{"company_name": {company_name!r}, "workstream": "FINANCIAL"}}'
            ),
            filters={"company_name": company_name, "workstream": "FINANCIAL"},
            notes="Multi-key AND — realistic pushdown shape for T2.",
        ),
        FilterCandidate(
            dimension="priority_tier",
            label=(
                f'company + tier lte '
                f'{{"company_name": {company_name!r}, "priority_tier <=": 2}}'
            ),
            filters={"company_name": company_name, "priority_tier <=": 2},
            notes="Multi-key AND — tier cap + tenant filter.",
        ),
    ]


def all_candidates(company_name: str) -> list[FilterCandidate]:
    return [
        _company_name_candidate(company_name),
        *_workstream_candidates(),
        *_priority_tier_candidates(),
        *_combined_candidates(company_name),
    ]


def _index_name_for_catalog(catalog: str) -> str:
    return f"{catalog}.ingestion.embeddings_index"


def _embed_probe_query(
    *,
    embedding_endpoint: str,
    query: str = "revenue growth historical financial statements",
) -> list[float]:
    import mlflow.deployments

    client = mlflow.deployments.get_deploy_client("databricks")
    response = client.predict(
        endpoint=embedding_endpoint,
        inputs={"input": [query]},
    )
    return response["data"][0]["embedding"]


def _probe_filters_json(
    w,
    *,
    index_name: str,
    query_embedding: list[float],
    filters: dict[str, Any],
    num_results: int = 5,
) -> tuple[ProbeStatus, str]:
    """Direct SDK probe — no retrieval.py fallback."""
    filters_json = json.dumps(filters)
    try:
        result = w.vector_search_indexes.query_index(
            index_name=index_name,
            columns=["chunk_id", "doc_id", "file_name"],
            query_vector=query_embedding,
            num_results=num_results,
            filters_json=filters_json,
        )
        count = len(result.result.data_array or [])
        return "pass", f"sdk_accepted result_count={count} filters_json={filters_json}"
    except Exception as exc:
        return "fail", f"sdk_rejected error={exc!r} filters_json={filters_json}"


def _rollup_dimension(
    rows: list[tuple[FilterCandidate, ProbeStatus, str]],
    dimension: Dimension,
) -> ProbeStatus:
    statuses = [status for cand, status, _ in rows if cand.dimension == dimension]
    if not statuses:
        return "pending"
    if any(s == "pass" for s in statuses):
        return "pass"
    if all(s == "fail" for s in statuses):
        return "fail"
    return "pending"


def main(
    spark,
    catalog: str,
    company_name: str,
    *,
    embedding_endpoint: str = "databricks-bge-large-en",
) -> dict[str, str]:
    """Run VS filter pushdown probes; return per-dimension summary.

    Returns:
        {"company_name": "pass"|"fail",
         "workstream": "pass"|"fail"|"pending",
         "priority_tier": "pass"|"fail"|"pending"}

    Also prints one log line per candidate for operator attestation.
    """
    if spark is None:
        print(
            "[vs_filter_pushdown_probe] No active SparkSession — "
            "cluster run required; dimension rows remain pending."
        )
        return {
            "company_name": "fail",
            "workstream": "pending",
            "priority_tier": "pending",
        }

    from databricks.sdk import WorkspaceClient

    index_name = _index_name_for_catalog(catalog)
    w = WorkspaceClient()
    query_embedding = _embed_probe_query(embedding_endpoint=embedding_endpoint)

    print(
        f"[vs_filter_pushdown_probe] index={index_name!r} "
        f"company_name={company_name!r} catalog={catalog!r}"
    )

    probe_rows: list[tuple[FilterCandidate, ProbeStatus, str]] = []
    for candidate in all_candidates(company_name):
        status, detail = _probe_filters_json(
            w,
            index_name=index_name,
            query_embedding=query_embedding,
            filters=candidate.filters,
        )
        probe_rows.append((candidate, status, detail))
        print(
            f"[vs_filter_pushdown_probe] dimension={candidate.dimension} "
            f"status={status} label={candidate.label} :: {detail}"
        )

    summary = {
        "company_name": _rollup_dimension(probe_rows, "company_name"),
        "workstream": _rollup_dimension(probe_rows, "workstream"),
        "priority_tier": _rollup_dimension(probe_rows, "priority_tier"),
    }
    print(f"[vs_filter_pushdown_probe] summary={summary}")
    return summary


def main_from_params() -> dict[str, str]:
    """Notebook/job entrypoint — resolves spark + widgets then calls main()."""
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from pyspark.sql import SparkSession

    spark = SparkSession.getActiveSession()
    catalog = get_param("catalog", default="uc13")
    company_name = get_param("sp_company_name")
    embedding_endpoint = get_param("embedding_endpoint", default="databricks-bge-large-en")

    return main(
        spark,
        catalog,
        company_name,
        embedding_endpoint=embedding_endpoint,
    )


if __name__ == "__main__":
    main_from_params()

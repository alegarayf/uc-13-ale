"""IntentScopeResolver — spec §5.12.10."""

from __future__ import annotations

from collections.abc import Sequence

from eval.retrieval.errors import ScopeMismatchError, ScopeResolutionError
from eval.retrieval.models import GoldLabel, RetrievalIntent

GLOBAL_RETRIEVAL_PATHS = frozenset(
    {
        "databricks/agents/shared/retrieval.py",
        "databricks/agents/subagents/workstream/financial/context_utils.py",
    }
)

REGISTRY_OR_GOLD_SUFFIXES = (
    "intent_registry.yaml",
    "gold_labels/",
)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _is_global_retrieval_change(path: str) -> bool:
    normalized = _normalize_path(path)
    return normalized in GLOBAL_RETRIEVAL_PATHS


def _is_registry_or_gold_change(path: str) -> bool:
    normalized = _normalize_path(path)
    return any(
        normalized.endswith(suffix) or suffix in normalized
        for suffix in REGISTRY_OR_GOLD_SUFFIXES
    )


def is_gate_eligible(gold: GoldLabel) -> bool:
    """Gate-eligible per §5.12.1 — ready/partial with ≥1 positive."""
    if gold.gold_status not in {"ready", "partial"}:
        return False
    return len(gold.positive_chunk_ids) >= 1


def gate_eligible_intent_ids(
    gold_labels: Sequence[GoldLabel],
    *,
    company_name: str,
    catalog: str,
) -> list[str]:
    return sorted(
        label.intent_id
        for label in gold_labels
        if label.company_name == company_name
        and label.catalog == catalog
        and is_gate_eligible(label)
    )


class IntentScopeResolver:
    """Compute enhancement PR scope from git diff + registry."""

    def resolve(
        self,
        git_diff_paths: Sequence[str],
        registry: Sequence[RetrievalIntent],
        *,
        gold_labels: Sequence[GoldLabel] | None = None,
        company_name: str | None = None,
        catalog: str | None = None,
    ) -> dict[str, list[str]]:
        paths = [_normalize_path(path) for path in git_diff_paths if path]
        if not paths:
            raise ScopeResolutionError("git_diff_paths is empty")

        registry_list = list(registry)
        if not registry_list:
            raise ScopeResolutionError("registry is empty")

        tenant_catalog = catalog or registry_list[0].catalog
        tenant_name = company_name or "Elder Care"
        if gold_labels:
            sample = gold_labels[0]
            tenant_name = company_name or sample.company_name
            tenant_catalog = catalog or sample.catalog

        global_change = any(_is_global_retrieval_change(path) for path in paths)
        agent_paths = {
            path
            for path in paths
            if not _is_global_retrieval_change(path)
            and not _is_registry_or_gold_change(path)
        }
        metadata_only = all(_is_registry_or_gold_change(path) for path in paths)

        if metadata_only and not global_change:
            raise ScopeResolutionError(
                "registry or gold label changes require explicit declared_affected_intents "
                "in PR scope validation"
            )

        if global_change:
            affected = sorted({intent.intent_id for intent in registry_list})
        else:
            affected_set: set[str] = set()
            for intent in registry_list:
                source = _normalize_path(intent.source_file)
                if any(
                    source == agent_path or source.endswith(agent_path)
                    for agent_path in agent_paths
                ):
                    affected_set.add(intent.intent_id)
            if not affected_set:
                raise ScopeResolutionError(
                    f"no registry intents matched changed paths: {sorted(agent_paths)}"
                )
            affected = sorted(affected_set)

        gated: list[str]
        if gold_labels is not None:
            eligible = set(
                gate_eligible_intent_ids(
                    gold_labels,
                    company_name=tenant_name,
                    catalog=tenant_catalog,
                )
            )
            gated = sorted(intent_id for intent_id in affected if intent_id in eligible)
        else:
            gated = list(affected)

        return {
            "affected_intents": affected,
            "gated_intents": gated,
        }

    def validate_pr_scope(
        self,
        declared_affected: Sequence[str],
        declared_gated: Sequence[str],
        computed: dict[str, list[str]],
    ) -> None:
        expected_affected = sorted(declared_affected)
        expected_gated = sorted(declared_gated)
        if sorted(computed.get("affected_intents", [])) != expected_affected:
            raise ScopeMismatchError(
                "declared affected_intents do not match computed scope: "
                f"declared={expected_affected}, computed={computed.get('affected_intents')}"
            )
        if sorted(computed.get("gated_intents", [])) != expected_gated:
            raise ScopeMismatchError(
                "declared gated_intents do not match computed scope: "
                f"declared={expected_gated}, computed={computed.get('gated_intents')}"
            )

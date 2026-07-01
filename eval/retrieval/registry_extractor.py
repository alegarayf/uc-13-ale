"""Static AST extractor for retrieval intent registry — spec §5.12.6."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import yaml

from eval.retrieval.models import RetrievalIntent

DEFAULT_CATALOG = "uc13_ale"

RETRIEVAL_CALLS = frozenset(
    {"semantic_search", "semantic_search_with_fallback", "_semantic_search_with_fallback"}
)
WRAPPER_DEF_NAMES = frozenset(
    {"semantic_search_with_fallback", "_semantic_search_with_fallback"}
)

AGENT_ID_BY_STEM: dict[str, str] = {
    "kpi_agent": "kpi",
    "customer_quality_agent": "cqa",
    "quality_of_earnings_agent": "qoe",
    "business_model_agent": "bma",
    "legal_contracts_agent": "legal",
    "opex_sub_agent": "fta.opex",
    "revenue_sub_agent": "fta.revenue",
    "ebitda_sub_agent": "fta.ebitda",
    "company_profiler": "profiler",
}

PROFILER_DIMENSIONS: tuple[str, ...] = (
    "industry_overlay",
    "revenue_model",
    "business_description",
    "company_size_indicators",
    "deal_type",
    "banked_vs_nonbanked",
    "vertical_subsector",
)

LEGAL_PASS_IDS: tuple[str, ...] = (
    "contracts_vendors_platform",
    "employment",
    "litigation",
    "ip_privacy",
    "insurance",
)

FTA_INTENT_SUFFIXES: dict[tuple[str, int], str] = {
    ("fta.opex", 1): "q1_financial_statements",
    ("fta.opex", 2): "q2_working_capital",
    ("fta.opex", 3): "q3_projected_financials",
    ("fta.revenue", 1): "q1_financial_statements",
    ("fta.revenue", 2): "q2_revenue_by_segment",
    ("fta.revenue", 3): "q3_revenue_by_geography",
    ("fta.revenue", 4): "q4_customer_concentration",
    ("fta.revenue", 5): "q4_customer_concentration_fallback",
    ("fta.revenue", 6): "q5_quickbooks_pl",
    ("fta.ebitda", 1): "q1_financial_statements",
    ("fta.ebitda", 2): "q2_ebitda_and_margins",
    ("fta.ebitda", 3): "q3_working_capital",
    ("fta.ebitda", 4): "q4_addback_schedule",
}


def _repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _relative_source(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:48] or "query"


def _tool_suffix_from_function(name: str) -> str | None:
    if name.startswith("_tool_"):
        return name.removeprefix("_tool_")
    return None


def _literal_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal_value(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_value(elt) for elt in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal_value(node.operand)
        if isinstance(inner, int | float):
            return -inner
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
        return "".join(parts) if parts else None
    return None


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_kwargs(call: ast.Call) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        value = _literal_value(keyword.value)
        if value is not None:
            kwargs[keyword.arg] = value
    return kwargs


def _normalize_tier_filter(value: Any) -> int | None:
    if value is True:
        return 1
    if isinstance(value, int):
        return value
    return None


def _query_string(kwargs: dict[str, Any], fallback: str = "") -> str:
    query = kwargs.get("query")
    if isinstance(query, str) and query.strip():
        return " ".join(query.split())
    return fallback


class _IntentVisitor(ast.NodeVisitor):
    def __init__(self, source_file: str, agent_id: str, *, skip_profiler_loop: bool) -> None:
        self.source_file = source_file
        self.agent_id = agent_id
        self.skip_profiler_loop = skip_profiler_loop
        self.intents: list[RetrievalIntent] = []
        self._function_stack: list[str] = []
        self._fta_query_index = 0
        self._in_wrapper_def = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self._in_wrapper_def = node.name in WRAPPER_DEF_NAMES
        self.generic_visit(node)
        self._function_stack.pop()
        self._in_wrapper_def = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name not in RETRIEVAL_CALLS:
            self.generic_visit(node)
            return

        if name == "semantic_search" and self._in_wrapper_def:
            self.generic_visit(node)
            return

        if self.skip_profiler_loop and name == "semantic_search":
            self.generic_visit(node)
            return

        kwargs = _extract_kwargs(node)
        invocation_path: str
        if name in WRAPPER_DEF_NAMES:
            invocation_path = "with_fallback"
        else:
            invocation_path = "direct"

        tool_suffix = _tool_suffix_from_function(self._function_stack[-1]) if self._function_stack else None
        if tool_suffix:
            intent_suffix = tool_suffix
        elif self.agent_id.startswith("fta."):
            self._fta_query_index += 1
            intent_suffix = FTA_INTENT_SUFFIXES.get(
                (self.agent_id, self._fta_query_index),
                f"q{self._fta_query_index}_{_slugify(_query_string(kwargs, 'query'))}",
            )
        else:
            intent_suffix = _slugify(_query_string(kwargs, "query"))

        intent_id = f"{self.agent_id}.{intent_suffix}"
        catalog = kwargs.get("catalog")
        if not isinstance(catalog, str):
            catalog = DEFAULT_CATALOG

        tier_filter = _normalize_tier_filter(kwargs.get("tier_filter"))
        top_k = kwargs.get("top_k")
        if not isinstance(top_k, int):
            top_k = 10

        intent = RetrievalIntent(
            intent_id=intent_id,
            agent_id=self.agent_id,
            source_file=self.source_file,
            catalog=catalog,
            query=_query_string(kwargs, intent_suffix.replace("_", " ")),
            workstream_filter=kwargs.get("workstream_filter"),
            file_name_filter=kwargs.get("file_name_filter"),
            top_k=top_k,
            min_chunk_length=kwargs.get("min_chunk_length"),
            min_results=kwargs.get("min_results"),
            source_type_priority=kwargs.get("source_type_priority"),
            source_type_filter=kwargs.get("source_type_filter"),
            tier_filter=tier_filter,
            retrieval_mode=kwargs.get("retrieval_mode"),
            invocation_path=invocation_path,  # type: ignore[arg-type]
            extraction_confidence="static",
        )
        self.intents.append(intent)
        self.generic_visit(node)


def _profiler_intents(source_file: str) -> list[RetrievalIntent]:
    intents: list[RetrievalIntent] = []
    queries: dict[str, tuple[str, list[str], list[str]]] = {
        "industry_overlay": (
            "industry sector service type end market vertical",
            ["CIM", "Business", "Overview", "Summary", "Profile"],
            ["BUSINESS_MODEL"],
        ),
        "revenue_model": (
            "revenue model contract type recurring revenue subscription retainer",
            ["CIM", "Business", "Overview", "Summary", "Profile"],
            ["BUSINESS_MODEL"],
        ),
        "business_description": (
            "company description what the company does services offered overview",
            ["CIM", "Business", "Overview", "Summary", "Profile"],
            ["BUSINESS_MODEL"],
        ),
        "company_size_indicators": (
            "revenue headcount EBITDA gross margin employees size scale",
            ["CIM", "Financial", "P&L", "Profit", "EBITDA"],
            ["FINANCIAL", "BUSINESS_MODEL"],
        ),
        "deal_type": (
            "buyout growth equity recapitalization transaction type deal structure",
            ["CIM", "Business", "Overview", "Summary"],
            ["BUSINESS_MODEL"],
        ),
        "banked_vs_nonbanked": (
            "CIM offering memorandum banker investment bank process",
            ["CIM", "Offering", "OM"],
            ["BUSINESS_MODEL"],
        ),
        "vertical_subsector": (
            "sub-sector specialty product lines service lines niche segment",
            ["CIM", "Business", "Overview", "Summary", "Profile"],
            ["BUSINESS_MODEL"],
        ),
    }
    for dimension in PROFILER_DIMENSIONS:
        query, fn_filter, ws_filter = queries[dimension]
        intents.append(
            RetrievalIntent(
                intent_id=f"profiler.{dimension}",
                agent_id="profiler",
                source_file=source_file,
                catalog=DEFAULT_CATALOG,
                query=query,
                workstream_filter=ws_filter,
                file_name_filter=fn_filter,
                top_k=5,
                min_chunk_length=100,
                tier_filter=1,
                invocation_path="direct",
                extraction_confidence="static",
            )
        )
    return intents


def _legal_intents(source_file: str) -> list[RetrievalIntent]:
    queries = {
        "contracts_vendors_platform": (
            "material customer contract MSA master service agreement statement of work "
            "change of control termination vendor supplier platform reseller channel "
            "staffing agreement lease sublease asset purchase marketing contract"
        ),
        "employment": (
            "employment agreement offer letter contractor commission plan founder key employee "
            "employee handbook orientation restricted stock non-compete non-solicit "
            "severance 401k bylaws staffing agreement"
        ),
        "litigation": (
            "litigation lawsuit dispute regulatory compliance arbitration demand letter "
            "settlement survey DOH approval bond renewal regulatory correspondence "
            "threatened claim legal engagement letter"
        ),
        "ip_privacy": (
            "intellectual property IP ownership assignment data privacy GDPR HIPAA "
            "indemnification liability cap open source OSS data processing agreement BAA"
        ),
        "insurance": (
            "insurance certificate policy COI certificate of insurance indemnity "
            "coverage bond renewal liability unusual indemnity"
        ),
    }
    budgets = {
        "contracts_vendors_platform": {
            "top_k": 14,
            "min_chunk_length": 150,
            "file_name_filter": [
                "Contract", "MSA", "Agreement", "SOW", "Customer", "Client", "Vendor", "Supplier",
                "SA", "Lease", "Sublease", "Staffing", "Purchase", "Temp", "Marketing", "Engagement",
            ],
        },
        "employment": {
            "top_k": 10,
            "min_chunk_length": 150,
            "file_name_filter": [
                "Employment", "Offer", "Contractor", "Commission", "Founder",
                "Handbook", "Orientation", "401", "Restricted", "Stock", "Bylaws",
            ],
        },
        "litigation": {
            "top_k": 8,
            "min_chunk_length": 150,
            "file_name_filter": [
                "Litigation", "Dispute", "Legal", "Demand", "Regulatory",
                "Survey", "DOH", "Bond", "Compliance", "Engagement",
            ],
        },
        "ip_privacy": {
            "top_k": 8,
            "min_chunk_length": 150,
            "file_name_filter": [
                "IP", "Privacy", "GDPR", "HIPAA", "OSS", "Data Processing", "BAA",
            ],
        },
        "insurance": {
            "top_k": 6,
            "min_chunk_length": 150,
            "file_name_filter": [
                "Insurance", "Policy", "COI", "Indemnity", "Bond", "Renewal",
            ],
        },
    }
    intents: list[RetrievalIntent] = []
    for pass_id in LEGAL_PASS_IDS:
        budget = budgets[pass_id]
        intents.append(
            RetrievalIntent(
                intent_id=f"legal.{pass_id}",
                agent_id="legal",
                source_file=source_file,
                catalog=DEFAULT_CATALOG,
                query=queries[pass_id],
                workstream_filter=["LEGAL"],
                file_name_filter=budget["file_name_filter"],
                top_k=budget["top_k"],
                min_chunk_length=budget["min_chunk_length"],
                min_results=3,
                invocation_path="with_fallback",
                extraction_confidence="static",
            )
        )
    return intents


def _scan_paths(repo_root: Path) -> list[Path]:
    agents_root = repo_root / "databricks" / "agents"
    paths = sorted(agents_root.rglob("*.py"))
    profiler = repo_root / "databricks" / "jobs" / "scripts" / "company_profiler.py"
    if profiler.exists():
        paths.append(profiler)
    return paths


def _agent_id_for_path(path: Path) -> str | None:
    stem = path.stem
    if stem in AGENT_ID_BY_STEM:
        return AGENT_ID_BY_STEM[stem]
    return None


class IntentRegistryExtractor:
    """Extract RetrievalIntent records from agent retrieval call sites."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or _repo_root_from_here()

    def extract(self) -> list[RetrievalIntent]:
        intents: list[RetrievalIntent] = []
        for path in _scan_paths(self.repo_root):
            agent_id = _agent_id_for_path(path)
            if agent_id is None:
                continue

            source_file = _relative_source(path, self.repo_root)
            if agent_id == "profiler":
                intents.extend(_profiler_intents(source_file))
                continue

            if agent_id == "legal":
                intents.extend(_legal_intents(source_file))
                continue

            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            visitor = _IntentVisitor(
                source_file,
                agent_id,
                skip_profiler_loop=False,
            )
            visitor.visit(tree)
            intents.extend(visitor.intents)

        intents.sort(key=lambda item: item.intent_id)
        return intents

    def write_registry(self, output_path: Path | None = None) -> list[RetrievalIntent]:
        intents = self.extract()
        path = output_path or (self.repo_root / "eval" / "retrieval" / "intent_registry.yaml")
        payload = [intent.model_dump(mode="json", exclude_none=True) for intent in intents]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return intents

    @staticmethod
    def count_by_agent(intents: list[RetrievalIntent]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for intent in intents:
            counts[intent.agent_id] = counts.get(intent.agent_id, 0) + 1
        return counts

    @staticmethod
    def validate_counts(
        intents: list[RetrievalIntent],
        expected: dict[str, int],
        *,
        tolerance: int = 2,
        total_min: int = 49,
        total_max: int = 54,
    ) -> None:
        counts = IntentRegistryExtractor.count_by_agent(intents)
        total = len(intents)
        if total < total_min or total > total_max:
            raise ValueError(
                f"Total intent count {total} outside [{total_min}, {total_max}]"
            )

        for agent_id, target in expected.items():
            actual = counts.get(agent_id, 0)
            manual = sum(
                1
                for intent in intents
                if intent.agent_id == agent_id and intent.extraction_confidence == "manual"
            )
            if manual:
                continue
            if actual < target - tolerance or actual > target + tolerance:
                raise ValueError(
                    f"agent_id={agent_id} count {actual} outside [{target - tolerance}, {target + tolerance}]"
                )


def main() -> None:
    extractor = IntentRegistryExtractor()
    intents = extractor.write_registry()
    counts = extractor.count_by_agent(intents)
    print(f"Extracted {len(intents)} intents")
    for agent_id in sorted(counts):
        print(f"  {agent_id}: {counts[agent_id]}")


if __name__ == "__main__":
    main()

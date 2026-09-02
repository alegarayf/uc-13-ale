"""Static contract tests for AD-001 (.specs/STATE.md): every chat/vision call
to a Claude endpoint routes through agents/shared/llm_client.py -- no module
outside the gateway constructs its own mlflow.deployments client for one.

Mirrors tests/test_catalog_convention.py's AST-based static-scan style.

This is a REGRESSION GUARD, not a migration test: T13-T21 already migrated or
deliberately excluded every real call site (see spec.md's Out of Scope table
and STATE.md's AD-001/AD-002). This test exists so a future revert or a new
call site added without routing through the gateway fails loudly here,
instead of silently reintroducing the pre-migration pattern (11 separate
mlflow.deployments.get_deploy_client() call sites) that AD-001 eliminated.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCAN_ROOTS = ["databricks/agents", "databricks/jobs/scripts"]

# Every file allowed to construct its own mlflow.deployments deploy client,
# with the reason AD-001/AD-002 exempts it. Any file outside this list that
# does so is a violation -- either route it through llm_client.chat() or add
# it here with a documented reason (never silently).
_ALLOWED_RAW_CLIENT_FILES: dict[str, str] = {
    "databricks/agents/shared/llm_client.py": (
        "The gateway itself -- its _call_databricks() is the fallback path "
        "and the LLM_BACKEND=\"databricks\" path (AD-001)."
    ),
    "databricks/agents/shared/retrieval.py": (
        "Embeddings (databricks-bge-large-en). Anthropic has no embeddings "
        "API (AD-001)."
    ),
    "databricks/jobs/scripts/doc_worker.py": (
        "Embeddings via ingestion_parser.get_embeddings_batch (AD-001)."
    ),
    "databricks/jobs/scripts/ensure_coverage.py": (
        "Embeddings via ingestion_parser.get_embeddings_batch (AD-001)."
    ),
    "databricks/jobs/scripts/ingestion_parser.py": (
        "Embeddings (get_embeddings_batch, AD-001) AND the non-Claude branch "
        "of vision extraction: vision_endpoint is runtime-parametrized and "
        "its own code comment names a Llama vision model as a valid value "
        "(AD-002, T21)."
    ),
    "databricks/jobs/scripts/company_profiler.py": (
        "The non-Claude branch of call_llm(): llm_endpoint is runtime-"
        "parametrized and defaults to Llama on the standalone Phase 1-2 job "
        "(uc13_ingestion_pipeline.yml), Claude on Phase 1-5 "
        "(run_full_pipeline.py) (AD-002, T20)."
    ),
    "databricks/jobs/scripts/document_classifier.py": (
        "_CLASSIFIER_ENDPOINT is hardcoded to "
        "databricks-meta-llama-3-3-70b-instruct -- Llama, not Claude. "
        "Anthropic's SDK cannot serve it (AD-001, T19)."
    ),
    "databricks/jobs/scripts/vs_filter_pushdown_probe.py": (
        "Manual diagnostic script, not on any production path "
        "(spec.md Out of Scope)."
    ),
}


def _iter_python_files():
    for root in _SCAN_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path.relative_to(_REPO_ROOT).as_posix()


def _parse(rel_path: str) -> ast.Module:
    source = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    return ast.parse(source, filename=rel_path)


def _called_name(node: ast.Call) -> str | None:
    """The bare callee name of a call, for both `a.b()` and `b()`.

    Matching only `ast.Attribute` was a real bypass: `from mlflow.deployments
    import get_deploy_client` followed by `get_deploy_client("databricks")`
    parses as `ast.Name`, so it scored zero hits on both checks and slipped
    past the AD-001 guard entirely. T22's injected-violation evidence used the
    attribute form only, which is why the hole survived that task.
    """
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _find_get_deploy_client_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "get_deploy_client"
    ]


def _find_predict_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "predict"
    ]


def _string_literal_args(call: ast.Call) -> list[str]:
    """Every hardcoded string argument of a call -- positional and keyword.

    Deliberately broader than the old `_endpoint_literal()`, which read only
    `kw.arg == "endpoint"`. That was a second bypass of the same family as the
    ast.Name one: mlflow's signature is
    `predict(deployment_name=None, inputs=None, endpoint=None)`, so
    `client.predict("databricks-claude-sonnet-4-6", inputs={})` passes the
    endpoint positionally as `deployment_name` and scored zero hits -- a Claude
    call site bypassing the gateway with the guard green.

    The check this feeds asks "does any hardcoded Claude endpoint appear in a
    predict() call outside the gateway", so every literal is in scope, not just
    one blessed kwarg name. A variable or expression still yields nothing --
    that case is unknowable statically and is covered by the allowlist check.
    """
    literals = [
        arg.value
        for arg in call.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
    literals += [
        kw.value.value
        for kw in call.keywords
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
    ]
    return literals


@pytest.fixture(scope="module")
def _all_python_files() -> list[str]:
    return list(_iter_python_files())


def test_no_new_file_constructs_a_raw_deploy_client_outside_the_allowlist(_all_python_files):
    """A file calling mlflow.deployments.get_deploy_client() that isn't in
    _ALLOWED_RAW_CLIENT_FILES is either a reverted migration or an
    unreviewed new call site -- both must fail here, not ship silently."""
    violations = []
    for rel_path in _all_python_files:
        if rel_path in _ALLOWED_RAW_CLIENT_FILES:
            continue
        tree = _parse(rel_path)
        if _find_get_deploy_client_calls(tree):
            violations.append(rel_path)

    assert not violations, (
        "These files construct their own mlflow.deployments client without "
        "being in the AD-001 allowlist -- route through llm_client.chat() or "
        f"add them to _ALLOWED_RAW_CLIENT_FILES with a documented reason: {violations}"
    )


def test_no_predict_call_hardcodes_a_claude_endpoint_outside_the_gateway(_all_python_files):
    """Defense in depth beyond the allowlist check: even inside an allowed
    file (e.g. company_profiler.py's non-Claude branch), no .predict() call
    may pass a literal endpoint string containing "claude" -- that would mean
    a Claude call bypassing the gateway entirely."""
    gateway_file = "databricks/agents/shared/llm_client.py"
    violations = []
    for rel_path in _all_python_files:
        if rel_path == gateway_file:
            continue
        tree = _parse(rel_path)
        for call in _find_predict_calls(tree):
            for literal in _string_literal_args(call):
                if "claude" in literal.lower():
                    violations.append(f"{rel_path}: predict(... {literal!r} ...)")

    assert not violations, (
        f"Found .predict() calls hardcoding a Claude endpoint outside the "
        f"gateway: {violations}"
    )


def test_allowlist_entries_are_all_documented_with_a_reason():
    """Every allowlist entry must carry a non-trivial reason -- an empty or
    placeholder justification defeats the point of requiring one."""
    for rel_path, reason in _ALLOWED_RAW_CLIENT_FILES.items():
        assert (_REPO_ROOT / rel_path).is_file(), f"{rel_path} no longer exists"
        assert len(reason) > 20, f"{rel_path} has no real documented reason"


@pytest.mark.parametrize(
    ("rel_path", "expected_keyword"),
    [
        ("databricks/jobs/scripts/document_classifier.py", "Llama"),
        ("databricks/jobs/scripts/company_profiler.py", "AD-002"),
        ("databricks/jobs/scripts/ingestion_parser.py", "AD-002"),
    ],
)
def test_t19_t20_t21_findings_are_named_in_their_allowlist_reason(rel_path, expected_keyword):
    """Makes the T19/T20/T21 discoveries a checked fact, not just prose in
    tasks.md that nothing re-verifies."""
    assert expected_keyword in _ALLOWED_RAW_CLIENT_FILES[rel_path]


# --- Regression: the scanner must see both call shapes, not just `a.b()` ----


def test_scanner_detects_the_bare_name_import_form_of_get_deploy_client():
    """A directly-imported `get_deploy_client(...)` must not evade the guard.

    Before this, both finders required `isinstance(node.func, ast.Attribute)`,
    so this exact source scored zero hits and a new module could build a raw
    Claude deploy client in full view of a green suite. Found by the T24
    discrimination sensor, not by T22 -- T22's injected violation only ever
    used the `mlflow.deployments.get_deploy_client(...)` attribute form, so it
    could not have probed this shape.
    """
    source = (
        "from mlflow.deployments import get_deploy_client\n"
        "client = get_deploy_client('databricks')\n"
        "client.predict(endpoint='databricks-claude-sonnet-4-6', inputs={})\n"
    )
    tree = ast.parse(source, filename="<bare-name-form>")
    assert len(_find_get_deploy_client_calls(tree)) == 1
    assert len(_find_predict_calls(tree)) == 1


def test_scanner_still_detects_the_attribute_form():
    """The broadened matcher must not lose the shape T22 originally covered."""
    source = (
        "import mlflow.deployments\n"
        "client = mlflow.deployments.get_deploy_client('databricks')\n"
        "client.predict(endpoint='databricks-claude-sonnet-4-6', inputs={})\n"
    )
    tree = ast.parse(source, filename="<attribute-form>")
    assert len(_find_get_deploy_client_calls(tree)) == 1
    assert len(_find_predict_calls(tree)) == 1


# --- Regression: a Claude endpoint passed positionally must not slip past ---


@pytest.mark.parametrize(
    ("source", "shape"),
    [
        ("client.predict(endpoint='databricks-claude-sonnet-4-6', inputs={})", "keyword endpoint="),
        ("client.predict('databricks-claude-sonnet-4-6', inputs={})", "positional"),
        ("client.predict(deployment_name='databricks-claude-sonnet-4-6')", "keyword deployment_name="),
    ],
)
def test_claude_literal_is_detected_in_every_predict_call_shape(source, shape):
    """mlflow's signature is predict(deployment_name, inputs, endpoint), so the
    endpoint can arrive positionally or under either kwarg name. Reading only
    `endpoint=` let `predict('databricks-claude-...', inputs={})` bypass the
    guard -- verified by the T24 Verifier against the allowlisted
    company_profiler.py, where the whole file's suite stayed green.
    """
    call = _find_predict_calls(ast.parse(source, filename=f"<{shape}>"))[0]
    assert any("claude" in lit.lower() for lit in _string_literal_args(call)), shape


def test_a_non_claude_literal_is_not_flagged():
    """The broadened matcher must not turn every string into a violation."""
    call = _find_predict_calls(
        ast.parse("client.predict(endpoint='databricks-bge-large-en', inputs={})")
    )[0]
    assert not any("claude" in lit.lower() for lit in _string_literal_args(call))


def test_scan_roots_still_cover_both_production_trees(_all_python_files):
    """Pins the scan surface itself.

    Dropping a root from _SCAN_ROOTS silently shrinks every check in this file
    to nothing without failing anything -- the Verifier's mutation 13 survived
    exactly that way. Asserting the roots AND that each actually yields files
    keeps the guard from going vacuous.
    """
    assert _SCAN_ROOTS == ["databricks/agents", "databricks/jobs/scripts"]
    for root in _SCAN_ROOTS:
        assert any(p.startswith(root + "/") for p in _all_python_files), (
            f"{root} contributed no files to the scan -- the guard is vacuous for it"
        )

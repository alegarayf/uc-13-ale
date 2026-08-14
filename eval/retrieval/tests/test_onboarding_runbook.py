"""Onboarding runbook CLI parity — M4 T8."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from eval.retrieval.eval_debt import build_parser as build_eval_debt_parser
from eval.retrieval.exemptions import build_parser as build_exemptions_parser
from eval.retrieval.gold.bootstrap import build_parser as build_bootstrap_parser
from eval.retrieval.harness_cli import build_parser as build_harness_cli_parser
from eval.retrieval.ingest_preflight import build_parser as build_ingest_preflight_parser
from eval.retrieval.trust_statement import build_parser as build_trust_statement_parser

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNBOOK = _REPO_ROOT / "eval" / "program" / "onboarding_runbook.md"

_MODULE_PARSERS = {
    "eval.retrieval.gold.bootstrap": build_bootstrap_parser,
    "eval.retrieval.harness_cli": build_harness_cli_parser,
    "eval.retrieval.exemptions": build_exemptions_parser,
    "eval.retrieval.ingest_preflight": build_ingest_preflight_parser,
    "eval.retrieval.eval_debt": build_eval_debt_parser,
    "eval.retrieval.trust_statement": build_trust_statement_parser,
}

_PLACEHOLDER_SUBSTITUTIONS = (
    ('"<Display Name>"', '"Clearsulting"'),
    ("<Display Name>", "Clearsulting"),
    ("<intent>", "legal.evidence"),
    ("<fta_numeric|legal_register|exec_summary|null>", "legal_register"),
    ("<eliminates|narrows|null>", "eliminates"),
    ("<corpus_absent|corpus_thin|overlay_mismatch>", "corpus_thin"),
    ("<k=v>", "legal_doc_count=0"),
    ("<path>", "/tmp/gold.yaml"),
    ("<canonical_slug>", "clearsulting"),
    ("<surface>", "legal_register"),
    ("<kind>", "promotion_inputs"),
    ('"<condition>"', '"per-company legal golden checklist scored"'),
    ("<condition>", "per-company legal golden checklist scored"),
)


def _runbook_text() -> str:
    assert _RUNBOOK.is_file(), f"missing runbook: {_RUNBOOK}"
    return _RUNBOOK.read_text(encoding="utf-8")


def _extract_bash_commands(text: str) -> list[str]:
    blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    commands: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("python -m eval.retrieval."):
                commands.append(stripped)
    return commands


def _substitute_placeholders(command: str) -> str:
    result = command
    for needle, replacement in _PLACEHOLDER_SUBSTITUTIONS:
        result = result.replace(needle, replacement)
    return result


def _parse_runbook_command(command: str) -> None:
    normalized = _substitute_placeholders(command)
    tokens = shlex.split(normalized, posix=False)
    assert tokens[:2] == ["python", "-m"], f"expected python -m prefix: {command!r}"
    module = tokens[2]
    argv = tokens[3:]
    parser_factory = _MODULE_PARSERS.get(module)
    assert parser_factory is not None, f"no parser registered for module {module!r}"
    parser_factory().parse_args(argv)


def test_runbook_commands_match_cli_surface() -> None:
    commands = _extract_bash_commands(_runbook_text())
    assert commands, "runbook must contain at least one bash CLI block"
    for command in commands:
        _parse_runbook_command(command)


def test_runbook_has_no_retired_path_strings() -> None:
    text = _runbook_text()
    assert ".dev/eval-program/registry.yaml" not in text
    assert "contracts/evals/" not in text


def test_runbook_names_program_registry_hub() -> None:
    text = _runbook_text()
    assert "eval/program/registry.yaml" in text
    assert "intent registry" in text.lower()


def test_runbook_documents_serverless_cluster_path() -> None:
    text = _runbook_text()
    assert ".dev/onboarding_cluster_submit.py" in text
    assert "Cluster execution (serverless)" in text
    assert "bootstrap" in text
    assert "harness-baseline" in text
    assert ".dev/agent-databricks-recipes.md" in text
    assert "pyyaml" in text
    assert "pydantic>=2.0" in text
    assert "mlflow" in text
    assert "eval/retrieval/" in text
    assert "databricks/agents" in text


@pytest.mark.parametrize(
    "command",
    _extract_bash_commands(_RUNBOOK.read_text(encoding="utf-8"))
    if _RUNBOOK.is_file()
    else [],
    ids=lambda cmd: cmd.split()[2].rsplit(".", 1)[-1],
)
def test_each_runbook_command_parses_individually(command: str) -> None:
    _parse_runbook_command(command)

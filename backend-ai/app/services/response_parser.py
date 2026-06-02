import ast
import json
import re
from typing import Any


class ParseError(ValueError):
    pass


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise ParseError(f"Response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ParseError("Response JSON must be an object.")
    return parsed


def _balanced_brace_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) indices for top-level `{...}` spans (end exclusive)."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        quote = ""
        for j in range(i, n):
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    in_string = False
                continue
            if ch in ('"', "'"):
                in_string = True
                quote = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    spans.append((i, j + 1))
                    break
        i += 1
    return spans


def _candidate_json_strings(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in candidates:
            candidates.append(c)

    add(stripped)

    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL | re.IGNORECASE):
        add(match.group(1))

    for start, end in _balanced_brace_spans(stripped):
        add(stripped[start:end])

    return candidates


def _normalize_python_function(rule_config: dict[str, Any]) -> None:
    pf = rule_config.get("python_function")
    if not isinstance(pf, dict):
        return
    source = pf.get("source")
    if not source or not isinstance(source, str):
        return
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise ParseError(f"python_function.source is not valid Python: {exc}") from exc


def _payload_from_dict(payload: dict[str, Any], *, original_text: str) -> tuple[str, dict[str, Any]]:
    if "summary" in payload and "rule" in payload:
        summary = str(payload["summary"]).strip()
        rule_config = payload["rule"]
        if not isinstance(rule_config, dict):
            raise ParseError('"rule" must be a JSON object.')
        if not summary:
            raise ParseError('"summary" must be a non-empty string.')
        _normalize_python_function(rule_config)
        return summary, rule_config

    summary_match = re.search(
        r"##\s*Summary\s*\n+(.*?)(?=\n##\s*Rule configuration|\Z)",
        original_text,
        re.IGNORECASE | re.DOTALL,
    )
    summary = summary_match.group(1).strip() if summary_match else ""

    rule_config = payload
    if "rule" in payload and isinstance(payload["rule"], dict):
        rule_config = payload["rule"]

    if not isinstance(rule_config, dict):
        raise ParseError("Rule configuration must be a JSON object.")

    if not summary:
        summary = str(rule_config.get("description") or rule_config.get("name") or "Rule interpretation")

    return summary, rule_config


def _try_parse_candidate(candidate: str, *, original_text: str) -> tuple[str, dict[str, Any], bool] | None:
    try:
        payload = _parse_json_object(candidate)
        summary, rule_config = _payload_from_dict(payload, original_text=original_text)
    except ParseError:
        return None
    canonical = "summary" in payload and "rule" in payload
    return summary, rule_config, canonical


def parse_rules_interpretation(text: str) -> tuple[str, dict[str, Any]]:
    """Extract summary and rule JSON from a Genie / model response."""
    if not text.strip():
        raise ParseError("AI response was empty.")

    fallback: tuple[str, dict[str, Any]] | None = None
    canonical_matches: list[tuple[str, dict[str, Any]]] = []

    for candidate in _candidate_json_strings(text):
        parsed = _try_parse_candidate(candidate, original_text=text)
        if parsed is None:
            continue
        summary, rule_config, is_canonical = parsed
        if is_canonical:
            canonical_matches.append((summary, rule_config))
        elif fallback is None:
            fallback = (summary, rule_config)

    # Prefer the last canonical JSON object — models often echo examples first, answer last.
    if canonical_matches:
        return canonical_matches[-1]

    if fallback is not None:
        return fallback

    raise ParseError(
        "Could not read a rule from the AI response. "
        "Genie may have answered in plain text instead of JSON—try rephrasing your rule, "
        "or use Deny to request another attempt."
    )

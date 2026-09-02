# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - When a spec says an action happens at most once, assert the call count on the success path too, not only on the path where the action fails
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `llm-gateway` · harmful: 0
- features: anthropic-sdk-migration
- evidence: validation.md Sensor mutation 6; tests/test_llm_client_fallback.py:156-167 (llm-gateway)
- last seen: 2026-09-02T22:58:07Z

### L-002 - An AST convention scan must match both attribute calls and bare-name calls, or a from-import bypasses the guard silently
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `static-scan` · harmful: 0
- features: anthropic-sdk-migration
- evidence: validation.md Fix 2; tests/test_llm_gateway_convention.py:81-98 (static-scan)
- last seen: 2026-09-02T22:58:07Z

### L-003 - A connectivity gate needs a third outcome for reachable-but-rejected, because collapsing an HTTP error status into blocked inverts the fact the gate exists to establish
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `egress-gate` · harmful: 0
- features: anthropic-sdk-migration
- evidence: tasks.md T2 SPEC_DEVIATION; databricks/jobs/scripts/check_anthropic_egress.py (egress-gate)
- last seen: 2026-09-02T22:58:07Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_

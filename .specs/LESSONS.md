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

### L-004 - Pin a static guard's argument-extraction and scan-scope helpers with their own tests, not just its call matcher, or the guard can be defanged without any test failing
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `static-scan` · harmful: 0
- features: anthropic-sdk-migration
- evidence: validation.md round-2 sensor mutations 12 and 13; tests/test_llm_gateway_convention.py:113-120 and :23 (static-scan)
- last seen: 2026-09-02T23:22:28Z

### L-005 - Pin a static matcher's depth boundary as well as its breadth, because broadening it to nested nodes only adds false positives and no test will object
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `static-scan` · harmful: 0
- features: anthropic-sdk-migration
- evidence: validation.md round-3 sensor mutation 16; tests/test_llm_gateway_convention.py:130-139 (static-scan)
- last seen: 2026-09-02T23:46:27Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_

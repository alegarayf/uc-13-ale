Section:      failure-taxonomy
Version:      1.0.0
Last updated: 2026-06-20

**Layer framework:**

```
L0  Input integrity   — failures attributable to input data before any processing begins
L2  Model behavior    — failures in model output relative to the prompt
L3  Output validation — failures in structural or semantic validity of output
L5  Infrastructure    — failures in external systems or environment
```

**Additional layers:** none declared.

```
Taxonomy version: 1.0.0
Last updated:     2026-06-20

[none at this time — fill per project via addition protocol; pending user input (2026-06-20)]
```

Code-observed failure modes (candidates for user confirmation — not yet registered as cause classes):

| Observed / anticipated | Likely layer | One-line description |
|------------------------|--------------|----------------------|
| Genie returns plain text instead of JSON | L2 / L3 | `ParseError` in response_parser |
| Genie FAILED status or missing credentials | L5 | `GenieRulesError` → HTTP 502 |
| Databricks SQL connection / missing catalog | L5 | Health check or query throws |
| Vector Search unavailable | L5 | retrieval.py keyword fallback (degraded) |
| LLM output truncation (large schemas) | L2 | Documented token caps in databricks/CLAUDE.md |
| Invalid python_function.source from model | L3 | ast.parse guard in response_parser |
| Session deny limit exceeded | L0 | HTTP 409 on deny endpoint |

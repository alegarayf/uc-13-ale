# Anthropic SDK Migration Validation

## Validation: anthropic-sdk-migration — PASS ✅

**Result**: PASS

**Date**: 2026-09-02
**Spec**: `.specs/features/anthropic-sdk-migration/spec.md`
**Diff range**: `588aa516e3b0f57370d69c134be90f1d7cb2c654~1..HEAD` (HEAD = `7fc60fb`, 36 commits, T1–T27)
**Verifier**: independent sub-agent (author ≠ verifier)
**Round**: 3 of a maximum 3 — final
**Verdict**: ✅ **PASS**. Every gap raised across three rounds is closed and independently re-verified. One mutant survives; it has **no production reach by construction** (it can only make the guard stricter, never permissive) and is documented below rather than graded down.

---

## Round history

| Round | Commit verified | Verdict | Gaps raised | Outcome |
| ----- | --------------- | ------- | ----------- | ------- |
| 1 | `778005e` | ❌ FAIL | Blocker (ASDK-06 AC5 non-discriminating), Major (AD-001 bare-name bypass), Cosmetic (T24 count) | First two fixed in `c2a53d3`; third **withdrawn — my error** |
| 2 | `c2a53d3` | ✅ PASS | Minor (positional-`predict` bypass), graded non-blocking | Coordinator **overruled my grading** and fixed it in `7fc60fb` — correct call |
| 3 | `7fc60fb` | ✅ **PASS** | none with production reach | Feature ready |

**Note on round 2**: I graded the positional-`predict` bypass Minor and did not block on it. The coordinator overruled that and fixed it. On review, the overrule was right: a Claude call site bypassing the gateway with a green suite is precisely the failure AD-001 exists to prevent, the severity discount I applied leaned on "unlikely in practice" rather than "not reachable", and the fix cost one function. Recorded here because a Verifier's grading errors belong in the evidence trail alongside the author's.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1–T24 | ✅ Done | Unchanged. T24's `1152 passed` figure is correct as recorded — see round-1 withdrawal below. |
| T25 | ✅ Done | ASDK-06 AC5 fix. Re-verified round 2 and carried forward. |
| T26 | ✅ Done | AD-001 bare-name (`ast.Name`) bypass fix. Re-verified round 2 and carried forward. |
| **T27** | ✅ Done | Positional/`deployment_name` literal bypass + scan-scope pinning. Verified independently this round. |

`tasks.md` Phase 6 now carries T25, T26, T27 with edge `T26 → T27`. Each entry names the defect, the mechanism, and its re-injection evidence.

---

## Round-1 finding withdrawn: T24's `1152 passed` is correct

Reproduced here so the retraction stays with the evidence. I flagged T24's gate count as stale and recommended overwriting it with `1155`. That was wrong:

```
git merge-base --is-ancestor 323e156 23e04e1   -> true
git show --stat 23e04e1  -> tests/test_llm_client_real_sdk_call_shape.py | 114 +++ (new, 3 tests)
```

T24 (`323e156`) landed **before** the commit that added those 3 tests, so `1152` was the true count when its gate ran. Coverage went 1020 → 1152 → 1155 → 1157 → 1162, never decreasing. My error: I inferred staleness from *document order* in `tasks.md` (T23 appears above T24 but was closed last) without checking *commit order*. The author's chronology note is the correct remedy; overwriting the number would have falsified evidence of a gate that never ran at 1155.

---

## Spec-Anchored Acceptance Criteria — re-derived for ASDK-09

`7fc60fb` touched only `tests/test_llm_gateway_convention.py` and `tasks.md`. ASDK-09's Independent Test is the sole criterion whose coverage changed, so it is re-derived; everything else is carried forward.

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Independent Test: no file **outside the allowlist** builds a deploy client for a `claude` endpoint | scan detects the violation in every call shape | `tests/test_llm_gateway_convention.py:81-95` `_called_name()` resolving `ast.Attribute` **and** `ast.Name`; `:196-211`, `:214-224` — `assert len(_find_get_deploy_client_calls(tree)) == 1` on both import forms | ✅ PASS |
| Defense-in-depth: no `.predict()` outside the gateway passes a literal `claude` endpoint — **including inside allowlisted files** | violation detected regardless of argument position or kwarg name | `tests/test_llm_gateway_convention.py:113-139` `_string_literal_args()` collecting positional **and** keyword string literals; `:248-265` — `assert any("claude" in lit.lower() for lit in _string_literal_args(call))` parametrized over `endpoint=`, **positional**, and `deployment_name=` | ✅ **PASS — bypass closed** |
| Broadened matcher must not flag a legitimate non-Claude endpoint | no violation for `databricks-bge-large-en` | `tests/test_llm_gateway_convention.py:268-274` — `assert not any("claude" in lit.lower() for lit in _string_literal_args(call))` | ✅ PASS |
| Scan surface cannot silently shrink | both roots present **and** each contributes files | `tests/test_llm_gateway_convention.py:277-288` — `assert _SCAN_ROOTS == ["databricks/agents", "databricks/jobs/scripts"]` **and** `assert any(p.startswith(root + "/") for p in _all_python_files)` per root | ✅ PASS |
| Allowlist entries carry a real reason; T19/T20/T21 findings named | non-trivial justification; keyword present | `tests/test_llm_gateway_convention.py:169-174`, `:188` | ✅ PASS |

All other ASDK-09 criteria (the eight call-site delegations, AC2/AC3 vision shapes, AC4 embeddings, AC5 YAML defaults, AC6 `max_tokens`) carried forward from round 1.

### Carried forward, verified in earlier rounds, not re-derived

ASDK-01 `tests/test_llm_client_chat.py:88` · ASDK-02 `tests/test_llm_client_resolve.py:32`, `test_llm_client_chat.py:125` · ASDK-03 `tests/test_llm_client_resolve.py:39,50` · ASDK-04 `tests/test_llm_client_chat.py:119,124,141-142` · ASDK-05 `tests/test_llm_client_fallback.py:83-88,149` · **ASDK-06** `tests/test_llm_client_fallback.py:96-97` (round-2 fix, both branches) · ASDK-07 `tests/test_llm_client_errors.py:75-77` (`AuthenticationError-401` → `assert _is_retryable(exc) is False`) · ASDK-08 `tests/test_llm_client_credentials.py:66,75,87-88,95,114` · ASDK-10 `tests/test_llm_client_tracing.py:111-116,154,163-165,223,240` · ASDK-11 `tests/test_llm_client_usage.py:23,34,43,55`, `test_agent_base_token_summary.py:38,71,91` · ASDK-12 `signoffs/ASDK-12-parity.md`, `run_vdr_rainmaker.py:51` · ASDK-13/15 `tests/test_check_anthropic_egress.py`, `signoffs/ASDK-13-egress-gate.md` · ASDK-14 `platform-capabilities.md` §1–§4.

**Status**: ✅ All 36 spec criteria covered with a `file:line` citation and an assertion matching the spec-defined outcome. No gaps.

---

## Discrimination Sensor — cumulative across three rounds

Run in a throwaway `git worktree` at `7fc60fb`; the real tree was never mutated.

| # | Target | Mutation | Killed? |
| - | ------ | -------- | ------- |
| 1–5, 7, 8 | `llm_client.py` | Round 1: `extra_body`→direct kwarg; `_is_retryable` 5xx→`True`; `is_claude_endpoint`→`True`; usage field swap; drop `_record_fallback`; vision `media_type` hardcoded; `_resolved_backend`→`"anthropic"` | ✅ Killed (round 1) |
| 6 | `llm_client.py:488-490` | Duplicate `_call_databricks()` on the success path | ✅ Killed (round 2, T25) |
| 9 | `test_llm_gateway_convention.py` | `_called_name()` → attribute-only | ✅ Killed (round 2, T26) |
| 10 | `llm_client.py:476-479` | Retry `_call_anthropic()` before degrading — a *different* no-loop violation | ✅ Killed (round 2) |
| 11 | `test_llm_gateway_convention.py` | `_find_get_deploy_client_calls()` → `[]` | ✅ Killed (round 2) |
| 12 | `test_llm_gateway_convention.py:113` | **[re-check]** `_string_literal_args()` → `[]` | ✅ **Killed** — 3 failed (all three shape cases) |
| 13 | `test_llm_gateway_convention.py:23` | **[re-check]** `_SCAN_ROOTS` drops `jobs/scripts` | ✅ **Killed** — `test_scan_roots_still_cover_both_production_trees` |
| 14 | `test_llm_gateway_convention.py:130-134` | **[new]** Drop the **positional** half of `_string_literal_args()` | ✅ Killed — the `positional` param case only |
| 15 | `test_llm_gateway_convention.py:135-139` | **[new]** Drop the **keyword** half of `_string_literal_args()` | ✅ Killed — the `endpoint=` and `deployment_name=` cases |
| 16 | `test_llm_gateway_convention.py:130-134` | **[new]** Over-match: recurse into nested containers via `ast.walk(call)` | ❌ **SURVIVED — 1162 passed** (no production reach — see below) |
| 17 | `test_llm_gateway_convention.py:113` | **[new]** Extreme over-match: always return `["claude"]` | ✅ Killed — `test_a_non_claude_literal_is_not_flagged` **and** the main scan |
| 18 | `test_llm_gateway_convention.py:23,278` | **[new]** Swap a root for one with no `.py` files, updating the test's expected list to match | ✅ Killed — the "each root contributes files" clause |

**Sensor depth**: P0-full — 18 mutations across three rounds
**Result**: **17/18 killed**; the one survivor is directionally safe

### Direct exploit re-check

The round-2 exploit, re-run verbatim against `7fc60fb`. Appending to the **allowlisted** `databricks/jobs/scripts/company_profiler.py`:

```python
def _verifier_probe(client):
    return client.predict("databricks-claude-sonnet-4-6", inputs={})
```

Round 2: `8 passed` — bypass succeeded.
Round 3: **FAILED**, with a diagnostic naming the file and the literal:

```
AssertionError: Found .predict() calls hardcoding a Claude endpoint outside the gateway:
["databricks/jobs/scripts/company_profiler.py: predict(... 'databricks-claude-sonnet-4-6' ...)"]
```

Closed.

### Attacking `_string_literal_args()` for over-matching — the coordinator's question

The broadened matcher's new failure mode is false positives. Assessed directly:

**The realistic false-positive vector is already excluded.** `_string_literal_args()` collects only *top-level* string arguments — `call.args` entries and `call.keywords` values that are themselves `ast.Constant`. Prompt text nested inside `inputs={"messages": [{"content": "you are Claude..."}]}` is an `ast.Dict`, not a `Constant`, so it is **not** collected. That is the right boundary: the matcher is broad on *arity* (any position, any kwarg name) and narrow on *depth*. Verified empirically — zero nested `claude` literals exist inside any `predict()` call across both scan roots today.

**Mutation 16 shows that boundary is unpinned.** Broadening the matcher to `ast.walk(call)` — recursing into nested containers — survives the whole suite. If a future maintainer "improved" it that way, prompt text mentioning Claude would start failing the guard and no test would object.

**Why this does not block.** Mutation 16 can only make the guard *stricter*. It cannot permit a Claude call site to bypass the gateway; the failure mode is a noisy assertion, never a silent pass. It therefore has **no production reach**, which is the bar set for this round. It also produces no false positive on the tree as it stands today.

**Is the single negative case sufficient?** Yes, for the guard as written — mutation 17 (extreme over-match) is killed by `test_a_non_claude_literal_is_not_flagged` *and* by the main scan, so the negative case is a genuine discriminator, not decoration. What it does not pin is the depth boundary specifically. The residual false-positive surface today is narrow: a top-level string argument, to any call named `predict`, containing `"claude"`, that is not an endpoint. Worth knowing that `_find_predict_calls()` matches *any* callee named `predict` — a future `model.predict("claude_features.csv")` would trip it. All 7 `predict()` calls in scope today are deploy-client calls, so there is no collision. Recommended as documentation, not a fix: **one line in the `_string_literal_args()` docstring stating that only top-level literals are in scope, and that recursing would surface prompt text.**

### Are the new tests self-pinning?

The coordinator asked whether the new tests can themselves be silently gutted. Answering precisely: **no test suite tests its own assertions** — gutting any test body always "survives", which is why mutating a test's own `assert` is not an informative probe. The meaningful question is whether the *helpers* those tests depend on are pinned, and mutations 12, 14, 15, and 18 answer it:

- Both halves of `_string_literal_args()` have their own killing parametrized case (14, 15) — the parametrization is load-bearing, not decorative.
- `test_scan_roots_still_cover_both_production_trees`'s second clause is **not** redundant with its equality assertion. Mutation 18 changed `_SCAN_ROOTS` *and* the expected list together, so equality passed — and the "each root contributes files" clause still caught it. That clause earns its place.

**Isolation verified**: `git status --porcelain` before the sensor showed only the untracked `validation.md` I was replacing; after `git worktree remove --force` it is identical plus `mlflow.db`/`mlruns/` from my own gate run, both deleted afterward. No `git stash` used.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ — one helper replaced, five test cases added; no production code touched |
| Surgical changes | ✅ — exactly the one file named in the round-2 fix plan |
| No scope creep | ✅ — `_string_literal_args()` replaces `_endpoint_literal()` rather than being layered beside it |
| Matches patterns | ✅ — consistent with the file's existing AST-helper and parametrized-case style |
| Spec-anchored outcome check | ✅ — 36/36 criteria assert the spec's exact value |
| Per-layer Coverage Expectation met | ✅ — domain 1:1 with ACs; the convention guard now covers every call shape it claims to |
| Every test maps to a spec requirement | ✅ — the five new cases map to ASDK-09's Independent Test via T27 |
| Documented guidelines followed | ✅ — `pytest.ini`, root `conftest.py`, `AGENTS.md` §Local limits |

The docstring at `tests/test_llm_gateway_convention.py:116-129` states the rationale — that the check asks "does any hardcoded Claude endpoint appear in a `predict()` call", so every literal is in scope rather than one blessed kwarg name. That framing is correct and is what makes the fix general rather than a patch against my specific exploit.

**Lint**: `ruff check tests/test_llm_gateway_convention.py` → **exit 0, "All checks passed!"**

---

## Edge Cases

Carried forward — no production code changed in rounds 2 or 3. All seven verified:

- [x] Invalid `LLM_BACKEND` → `ValueError` naming valid values — `tests/test_llm_client_resolve.py:72-75`
- [x] `anthropic` missing → `ImportError` with install hint — `tests/test_llm_client_credentials.py:103`
- [x] `stop_reason == "max_tokens"` → partial text as-is — `tests/test_llm_client_chat.py:180`
- [x] `stop_reason == "refusal"` → exception naming the category, no degradation — `tests/test_llm_client_chat.py:191`; `tests/test_llm_client_fallback.py:138-141`
- [x] ThreadPoolExecutor: shared client, race-free counters — `tests/test_llm_client_credentials.py:114`; `tests/test_llm_client_fallback.py:198`
- [x] No `text` block → `""` + warning — `tests/test_llm_client_chat.py:207-208`
- [~] Fallback-counter observability in a serverless run — disclosed at `tasks.md` T23 with the mechanism (`llm_client.py:419`), the API limitation, and an explicit statement that SUCCESS does not prove absence. Honest and adequate; not re-litigated.

---

## Gate Check

- **Gate command**: `databricks/.venv/bin/ruff check tests/test_llm_gateway_convention.py && databricks/.venv/bin/python -m pytest tests/ -q`
- **Result**: **1162 passed, 0 failed, 34 skipped**; ruff exit 0. Independently run, not taken from the coordinator's report.
- **Test count before feature**: 1020 passed, 34 skipped
- **Trajectory**: 1020 → 1152 (T24) → 1155 (T23) → 1157 (T25/T26) → **1162** (T27). Monotonically increasing; never decreased at any point.
- **Delta vs baseline**: **+142 tests**, 0 lost.
- **Skipped tests**: 34 — unchanged from the pre-feature baseline; none introduced by this feature.
- **Failures**: none.
- **Assertion strength**: no assertion weakened at any point across the three rounds. `7fc60fb` replaces `_endpoint_literal()` with a strictly broader `_string_literal_args()` (more detections, never fewer) and adds five cases. The one deletion in the whole feature — `tests/test_agent_base_llm_timeout.py` — had its C33 coverage ported to `tests/test_llm_client_credentials.py:144-175` before removal, verified in round 1.

---

## Fix Plans

| Fix | Round | Severity | Status |
| --- | ----- | -------- | ------ |
| 1 — ASDK-06 AC5 non-discriminating on the success branch | 1 | Blocker | ✅ Resolved in T25; mutants 6 and 10 killed |
| 2 — AD-001 guard bypassed by bare-name import | 1 | Major | ✅ Resolved in T26; mutants 9 and 11 killed |
| 3 — T24 test count "stale" | 1 | Cosmetic | ⊘ **Withdrawn — my diagnosis was wrong** |
| 4 — positional `predict()` literal bypass + unpinned scan scope | 2 | Minor (graded), **overruled to blocking** | ✅ Resolved in T27; mutants 12, 13, 14, 15, 18 killed; exploit re-check fails as it should |
| 5 — `_string_literal_args()` depth boundary unpinned | 3 | Documentation only | ○ Open, non-blocking — see below |

### Fix 5 (new, documentation only) — not a fix task

- **Root cause**: `_string_literal_args()` (`tests/test_llm_gateway_convention.py:130-139`) deliberately collects only top-level string literals, which correctly excludes prompt text nested in `inputs={...}`. No test pins that depth boundary, so mutation 16 (recursing via `ast.walk`) survives.
- **Why it is not a fix task**: the mutation can only make the guard stricter. It cannot admit a gateway bypass — the failure mode is a false positive, never a silent pass — so it has no production reach. It also produces no false positive on the current tree.
- **Suggested action**: one sentence in the `_string_literal_args()` docstring recording that only top-level literals are in scope and that recursing would surface prompt text. Optional; ordinary maintenance.

---

## Requirement Traceability Update

| Requirement | Status | Basis |
| ----------- | ------ | ----- |
| ASDK-01–05, 07, 08, 10–15 | ✅ Verified | Round 1, carried forward |
| ASDK-06 | ✅ Verified | Round 2 — AC5 discriminating on both branches (mutants 6, 10 killed) |
| ASDK-09 | ✅ Verified | Round 3 — Independent Test shape-complete and non-vacuous (mutants 9, 11, 12, 13, 14, 15, 17, 18 killed; exploit re-check fails as designed) |

**No change to `spec.md` is required** — all 15 rows correctly read `Verified`.

---

## Summary

**Overall**: ✅ **Ready.** No open blocker, no surviving mutant with production reach.

**Spec-anchored check**: 36/36 criteria matched the spec-defined outcome with a `file:line` citation.
**Sensor**: 18 mutations across three rounds, **17 killed**. The single survivor (16) can only over-match, never permit a bypass.
**Gate**: 1162 passed, 0 failed, 34 skipped (+142 vs the 1020 baseline, 0 lost), ruff exit 0.

**What works**: The gateway itself was strong from round 1 — the `extra_body` regression test is the only test in the suite exercising the real SDK signature and it genuinely reproduces the production `TypeError`; 401 is provably excluded from the fallback so an invalid key fails hard rather than degrading into a hollow deliverable; both AD-002 call sites pin the non-Claude branch instead of relying on `ValueError`. What the three rounds added is that the *guards around it* now discriminate too: ASDK-06 AC5 is pinned on the branch that matters, and the AD-001 convention scan detects every call shape it claims to — verified by re-running the exact exploit that defeated it one round earlier.

**Issues found**: One documentation-only residual (Fix 5). Nothing blocking.

**On the round-2 overrule**: the coordinator was right and I was wrong to grade the positional bypass as Minor. My discount rested on "unlikely in practice" rather than "not reachable", and reachability is the correct test for a guard whose entire purpose is catching what review misses. Deliberately **not** recorded as a lesson: it is guidance about how to run verification, which `lessons.md` scope discipline excludes from the project-local lessons layer. It is recorded here in the evidence trail instead.

**Next steps**: Feature is done. Fix 5 is optional maintenance and does not gate delivery.

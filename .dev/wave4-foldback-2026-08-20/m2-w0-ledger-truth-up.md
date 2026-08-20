# M2 / W0 — Ledger Truth-Up — exit verification

**Date:** 2026-08-20  
**Plan:** `.dev/plans/eval-signal-foldback-m2-ledger-truth-up/plan.md` v0.1.0

## §6 four-row check

| Spec §6 row | Result | Evidence |
|---|---|---|
| Ledger schemas parse | **pass** | `yaml.safe_load` on `registry.yaml`, `eval_debt/eval_debt.yaml`, `product_backlog.yaml`, `source_manifest.yaml` — stdout: `all four parse` |
| Sizing complete and in-vocabulary | **pass** | `test_actionable_registry_rows_have_d3_tshirt_sizes` (T1) — green in targeted run |
| `GAP-109` row exists after W0 | **pass** | `test_gap_109_cross_company_legal_kpi_g1_weakness_row_exists` (T2) — green in targeted run |
| Closure convention is uniform | **pass** | `test_product_backlog_exactly_four_closed_rows`, `test_product_backlog_rejects_orphan_closed_evidence_refs` (T4); `test_committed_ledger_ratchet_passes`, `test_spg_post_m4_corpus_dedup_debt_closed_with_d7_count` (T3 eval_debt close) — all green |

## Targeted pytest run

**Command:**

```
python -m pytest eval/retrieval/tests/test_eval_program_registry.py eval/retrieval/tests/test_eval_debt.py eval/retrieval/tests/test_product_backlog_schema.py -q
```

**Result:** `1 failed, 40 passed` in 1.49s (0 skipped)

**T1/T2/T3/T4 plan-owned tests (explicit re-run):** `6 passed` in 0.55s

**Pre-existing, out-of-scope failures present (expected, not regressions):** `test_populated_artifacts_pass_item_2a_validators` — registry `DISPOSITIONS` vs `disposition: resolved` on `GAP-M5-1-*` / `GAP-M5-3-*`; declared non-goal (plan §0 Flag 4 / M1 audit §7 row 4). Not introduced by T1–T5.

**New failures (if any — must be zero for this milestone's checkpoint to be green):** none

**Regression check vs scout SHA `fb4efa08a343009fc20874f1aeea89ff6b40da7b`:** no new failures beyond the named pre-existing registry-vocabulary test. T3 ratchet fix (`test_committed_ledger_ratchet_passes`) flipped from pre-existing fail to pass — positive change, not a regression.

## D7/D8 factual corrections landed

- SPG `44085` → `44038`: `registry.yaml` (`OI-eval-harness-post-m4-retrieval-baseline-refresh` rationale), `eval_debt.yaml` (`spg:global:post_m4_corpus_dedup_baseline_stale`, now closed), `product_backlog.yaml` (`PB-spg-ingest-borderline-completeness`, now closed).

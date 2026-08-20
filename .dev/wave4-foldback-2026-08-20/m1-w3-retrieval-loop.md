# M1 W3 — Retrieval enhancement/ablation loop (gate decision evidence)

**Date:** 2026-08-20  
**Plan:** `eval-signal-foldback-m1-retrieval-loop` · subtask T4  
**Charter:** M1 / W3 — Retrieval Enhancement/Ablation Loop  
**Enhancement measured:** `merge_rank_off` ablation arm (`--ablation-config '{"arm": "merge_rank_off"}'`) submitted as `run_type=enhancement` with gate-eligible `--affected-intents` (T3).

## Ops decision mechanism (Flag 1 resolution)

The recorded ops verdict for each retrieval harness run is **`gate_pass`** on `uc13_ale.ops.retrieval_harness_runs`, written by `finalize_run` during harness execution. There is no separate `promoted` / operator-decision column on that table for retrieval runs; `evaluate_promotion` applies to the e2e checklist gate (`promotion_gate.py`), not this retrieval delta loop.

Per playbook §6 step 4 and plan §4.5 step 5, the operator promote/reject read below names whether each enhancement `run_id` becomes the successor **`baseline_ref_run_id`** for future loop iterations (documentation action only — no registry or `trust_statement.py` baseline promotion in this subtask).

## Per-company gate decision

| Company | Pinned baseline (`baseline_ref_run_id`) | Enhancement `run_id` | Ops `gate_pass` | Operator promote/reject read | Successor `baseline_ref_run_id` for next loop |
|---|---|---|---|---|---|
| Elder Care | `baseline_2fa3a9056bd0` | `enhancement_61c90e6068bb` | `false` | **Reject** — degrading ablation arm; non-zero negative deltas on gated intents | `baseline_2fa3a9056bd0` (unchanged) |
| Clearsulting | `baseline_488f70f13570` | `enhancement_11db0ef8a7ea` | `false` | **Reject** | `baseline_488f70f13570` (unchanged) |
| GKF | `baseline_7510d1d14449` | `enhancement_540d38fe78a9` | `false` | **Reject** | `baseline_7510d1d14449` (unchanged) |
| SPG | `baseline_3992534e412f` | `enhancement_4e61af4d4c54` | `false` | **Reject** | `baseline_3992534e412f` (unchanged) |

All four companies: run-level `gate_pass=false` with measurable per-intent deltas (T3 kill criterion c not fired). Remote `validate-baseline` passed (semantic exit 0) for each pair — baseline ref integrity confirmed; rejection is on enhancement merit, not ref drift.

## Committed report artifacts

Force-added under `eval/retrieval/reports/` (gitignore exception, `baseline_2fa3a9056bd0.json` precedent):

- `enhancement_61c90e6068bb.json`
- `enhancement_11db0ef8a7ea.json`
- `enhancement_540d38fe78a9.json`
- `enhancement_4e61af4d4c54.json`

Source: Databricks workspace repo copy from T3 serverless harness runs; ops rows in `uc13_ale.ops.retrieval_harness_runs`, `_results`, `_deltas`.

## Upstream reference

T3 decision log: `.dev/plans/eval-signal-foldback-m1-retrieval-loop/decision-logs/T3.md`

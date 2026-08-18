# T4 signoff — Clearsulting W1 operator execution

**Plan:** eval-multi-company-coverage-expansion  
**Subtask:** T4  
**Operator date:** 2026-08-18  
**Catalog:** `uc13_ale`  
**Company:** Clearsulting (`clearsulting`)

## Verdict

**W1 complete per spec D3.** Trust statement regenerated with Clearsulting: retrieval attested; agent_fields/e2e partial (FTA linkage landed); S2 `fta_numeric` + `exec_summary` partial; `legal_register` known_gap (exempted). Twelve bloated-gold eval_debt rows remain open (documented below; re-bootstrap not required for W1).

## Run identifiers (labeled by system)

| Role | run_id | System |
|------|--------|--------|
| FTA pipeline agent manifest | `6e1b4f5d95284b33bbd08942b3595dd6` | `ops.retrieval_harness_runs` (`run_type=pipeline`, completed `2026-07-30T13:40:07`) |
| Prior FTA pipeline manifest (superseded score) | `d5e782836d5b4acb841ee960e49ad86a` | `ops.retrieval_harness_runs` + `ops.e2e_linkage` (16/18, 2026-07-07) |
| Retrieval harness baseline (latest) | `baseline_199cac401cd3` | `ops.retrieval_harness_latest_baseline` |
| S2 exec_summary spot-check | `20260818T231317Z-c894` | `uc13_ale.eval.s2_scores` |
| S2 fta_numeric spot-check | `20260818T231325Z-0a7e` | `uc13_ale.eval.s2_scores` |

**Analysis row used for G1/S2:** `uc13_ale.analysis.financial_trends` — `created_at=2026-07-30 13:40:00` (no post-Aug onboarding pipeline re-run; existing batch accepted for W1 scoring).

## Phase C — G1 / promotion

### G1 programmatic score

Command: `python .dev/g1_score_all_agents.py --company "Clearsulting"`

FTA weighted score **17/18** (16 pass, 2 partial, 0 miss). Golden checklist committed at `eval/FTA/golden_checklist_clearsulting.md`.

### Promotion / linkage

**Method:** warehouse SQL equivalent to `record_e2e_linkage` / `evaluate_promotion` promoted path (cluster submit blocked by workspace sync path error on nested `databricks/agents/.../assets` parent folder).

**Actions applied:**

1. `UPDATE uc13_ale.ops.retrieval_harness_runs` — set `e2e_agent_id=fta`, `e2e_snapshot_table=uc13_ale.analysis.financial_trends`, `e2e_checklist_score=17`, `e2e_checklist_total=18` on run `6e1b4f5d95284b33bbd08942b3595dd6`.
2. `INSERT uc13_ale.ops.e2e_linkage` — same run/score (idempotent guard).

**Outcome:** promoted vs prior Clearsulting FTA linkage (`d5e782…`, 16/18). Trust statement shows Clearsulting `agent_fields`/`e2e` **partial** (FTA + legacy legal linkage only; 2/7 agents).

**Eval debt:** `clearsulting:global:promotion_inputs` remains **open** — `closes_when` requires all agents; W1 scoped to FTA only per spec D3.

## Phase D — S2 (legal exempted)

| Surface | S2 run_id | Tally | Attestation |
|---------|-----------|-------|-------------|
| `legal_register` | — | skipped | `known_gap` / `corpus_absent` (exemption store) |
| `fta_numeric` | `20260818T231325Z-0a7e` | 0 supported / 276 unsupported | partial |
| `exec_summary` | `20260818T231317Z-c894` | 1 supported / 6 contradicted / 46 unsupported | partial |

**W1 caveat:** committed rubric manifests remain Elder Care–enumerated (`eval/content/*_rubric_claims.json`). Clearsulting W1 spot-check used T3 cache source resolution; high unsupported rate is expected until company-specific manifest regeneration (playbook §4.2 step 11). Failures are documented product/eval signal, not waivers.

Local operator packets (not required for attestation): `eval/content/spot-check/*_clearsulting*.yaml`.

## Phase E — Eval debt / bloated gold

**Twelve bloated `filename_closure` rows** (`clearsulting:global:bloated_fc_*`) remain open in `eval/program/eval_debt/eval_debt.yaml`. Status unchanged; aggregate retrieval attestation stands with documented caveats (T11 disposition). Re-bootstrap optional — not required for W1 (spec D3).

**HWM:** 14 — no new rows opened; no closure in this subtask.

## Phase E — Trust statement

Command: `python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml`

Generated: `2026-08-18T23:14:04Z` — Clearsulting rows match D3 minimum (see `eval/program/trust_statement.md`).

## Registry actions (T4)

1. **Created** `M5-S3-clearsulting-w1-complete` — operator-attested W1 close.
2. **Updated** `OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg` — Flag 7 disposition from `pending`/S1 using this signoff (Clearsulting FTA promotion evidence; GKF/SPG deferred W2).

## Kill-criterion evidence

| Criterion | Evidence |
|-----------|----------|
| No invented run_ids | All IDs queried from `ops.retrieval_harness_runs`, `ops.e2e_linkage`, `eval.s2_scores` |
| T1 merged before step 8 | `trust_statement.py` live `fetch_e2e_linkage_rows` / partial Clearsulting agent_fields |
| eval_debt HWM | No new rows; HWM stays 14 |
| OI row updated | Registry edit + this signoff |
| D3 minimum | Trust statement Clearsulting rows cited above |

## Adversarial gap (deferred)

No hermetic test that warehouse SQL promotion writes match `evaluate_promotion` Spark path byte-for-byte — cluster sync failure forced SQL equivalent; live linkage + trust regen are falsifiers.

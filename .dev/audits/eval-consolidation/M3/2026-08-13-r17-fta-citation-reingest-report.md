# R17 rung-3 re-ingest report — fta_numeric citation restoration (O-1 data half; D10)

**Subtask:** R17 · **Date:** 2026-08-13 · **Catalog:** `uc13_ale` · **Company:** `Elder Care`

## Summary

Re-ingested `fta_numeric` through R16's corrected shipped producer `write_spot_check_results` (no gitignored draft dependency; `ChunkIndex.lookup` no-match floor). Supersedes R13 run `20260813T205647Z-9fc2` with new run **`20260813T230816Z-0aed`**. Claim/magnitude/unit counts unchanged at R13 levels (276 / 119 / 35). **205** citation/locator triples moved vs the R13-landed set; **0** verdict or rationale movement.

## Run ID supersession

| Surface | Prior latest (R13) | R17 latest | Action |
|---------|-------------------|------------|--------|
| `fta_numeric` | `20260813T205647Z-9fc2` | **`20260813T230816Z-0aed`** | Re-ingested via R16-fixed producer |
| `exec_summary` | `20260813T185002Z-5a1b` | `20260813T185002Z-5a1b` | **Unchanged** |
| `legal_register` | `20260813T183720Z-r3f` | `20260813T183720Z-r3f` | Unchanged (not in R17 scope) |

Prior runs remain in `s2_scores` (never deleted).

## Citation restoration (`fta_numeric`)

| Metric | R13 run `…9fc2` | R17 run `…0aed` | Delta |
|--------|----------------:|----------------:|------:|
| Claims | 276 | 276 | 0 |
| `asserted_magnitude` non-null | 119 | 119 | 0 |
| `asserted_unit` non-null | 35 | 35 | 0 |
| Cited claims (`cited_chunk_id` non-null) | 276 | **194** | −82 |
| Citation triple divergences vs R13 | — | **205** | fix |
| Verdict flips | — | **0** | PASS (KC2) |
| Rationale changes | — | **0** | PASS (KC2) |

**Divergence breakdown (205 total):**

| Change class | Count | Source |
|--------------|------:|--------|
| Citation nulled (no-match floor, O-2) | 82 | R16 `ChunkIndex.lookup` returns `None` when no candidate scores |
| Chunk/locator reassigned (both non-null) | 123 | R16 draft removal (O-1) — committed manifest + chunk index only |
| **Total unique divergences** | **205** | |

The rev-3 audit probe (`rev3_probe_draft_dependency.py`) measured **133** divergences for **draft removal alone** (draft-present vs draft-absent, with the pre-R16 fabricated fallback still active). R17 applies the **full R16 fix** (draft removal **and** no-match floor), so 205 > 133 is expected — not a KC1 tripwire (KC1 binds claim/magnitude/unit counts, not citation divergence cardinality).

## Producer path (no one-off script)

```
write_spot_check_results(
  SpotCheckConfig(
    company="Elder Care",
    surface="fta_numeric",
    source="uc13_ale.analysis.financial_trends",
    verdicts_path=".dev/eval-program/spot-check/fta_numeric_elder_care_2026-08-13.verdicts.yaml",
    registry_path="eval/program/registry.yaml",
  ),
  writer=S2Writer(catalog="uc13_ale", sql_executor=make_sdk_sql_executor()),
)
```

Verdicts and rationales sourced unchanged from D1-attested YAML. S-61 resolver active; locators derived from resolved chunks (HALT-31).

## Kill-criterion evidence

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Claim/magnitude/unit counts match R13 (276 / 119 / 35) | **PASS** | Post-write SDK counts in `r17-citation-diff.json` `old_stats` / `new_stats` |
| 2 | No verdict-implying citation change | **PASS** | Warehouse diff: 0 verdict diffs, 0 rationale diffs; D10 covers provenance-only citation/locator movement |
| 3 | Operator D10 addendum signed | **PASS** | Signed addendum appended to `operator-attestation-rung3.md` §D10 |
| 4 | New citation set matches shipped producer (0 divergence) | **PASS** | `producer_vs_new_run_mismatch_count: 0` in `r17-citation-diff.json`; `test_fta_citation_set_reproducible_without_draft_artifact` PASS |

## Hermetic fixture match (KC4)

Live warehouse run `20260813T230816Z-0aed` citation triples match `load_claim_enumeration` output from the shipped producer against the live chunk index with **0** mismatches. R16 hermetic test `test_fta_citation_set_reproducible_without_draft_artifact` PASS (mocked index, 2-claim subset).

## Artifacts produced

| Path | Purpose |
|------|---------|
| `r17-citation-diff.json` | Old→new citation triples per claim (205 divergences) |
| `s2_scores_elder_care_dump.json` | Regenerated whole-table dump (1266 rows; +277 from new run) |
| `operator-attestation-rung3.md` | D10 addendum signed |
| `.dev/_r17_runner.py` | Ephemeral runner — **deleted post-execution** |

## Adversarial micro-pass deferral

No pytest for live warehouse re-ingest citation parity — post-write SDK producer-vs-warehouse diff (`producer_vs_new_run_mismatch_count: 0`) and dump `run_accounting` are the falsifiers (same deferral pattern as R13).

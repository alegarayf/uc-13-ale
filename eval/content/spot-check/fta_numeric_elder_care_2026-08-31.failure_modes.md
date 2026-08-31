# Failure-mode retriage — T9 fta_numeric spot-check, Elder Care (2026-08-31)

**Scope:** persist-vs-resolve of the 2026-08-13 FTA numeric claim-failure families on the live post-M4 corpus (`uc13_ale` Elder Care **55,819** chunks). Per-claim table: `fta_numeric_elder_care_2026-08-31.persist_vs_resolve.yaml`. Presentation packet: `fta_numeric_elder_care_2026-08-31.presentation.yaml`.

**Method:** Layer A = live `uc13_ale.analysis.financial_trends` (Elder Care, latest row `created_at` 2026-08-25). Layer B = full `chunk_text` from `uc13_ale.ingestion.chunks` for `2024 Elder Care - CIM_vF.pdf`, resolved through `load_claim_enumeration` + `ChunkIndex` (same post-guard path as `prepare_spot_check`). `prepare_spot_check` itself is currently unusable — `_assert_human_spot_check_allowed` raises when **any** MVP surface is `judge`, and CHK-26a now assigns `exec_summary: judge`.

Old 2026-08-13 chunk ids are **gone** (`027ec667…`, `cd9773ea…`, `b1feca18…`, `871ba744…` all count 0). Relocated ids used below.

## 1. Persist vs resolve (prior failure families)

| 2026-08-13 family | Prior n | 2026-08-31 status | Mechanism |
|---|---|---|---|
| **known_bad_chunk_family** (Pro Forma `027ec667…` placeholder) | 42 documented / 50 rationale-tagged in this re-scan | **resolved_relocation** (claim path) | Old ids gone. Resolution cites remapped sibling `2d238ee0-4136-4818-bb18-201b82990479` via `LOCATION_CHUNK_OVERRIDE`; magnitudes verbatim. Broken placeholder **still exists** as `aee7745d-e270-4abf-8fc5-c60dd4f13bcc` ("Five black, oval shapes…") — same text, new id. Zero claims cite the broken id. |
| **page46_b1feca18_not_verbatim** | 12 (`fta.claim.062`–`067`, `199`–`204`) | **resolved_relocation** | `b1feca18…` gone. New p.46 chunk `2b04d076-cfc0-49e3-9862-ef419f669c75` has Pro Forma Adjusted EBITDA **6,677 / 9,239** reconciling with **19.5% / 19.9%** margins. Stale 6,079 / 7,708 dollar-row is gone. All 12 verbatim. |
| **unresolvable_duplicate_array_rows** | 33 | **resolved_layer_a** | Not chunk relocation. Live `revenue_by_segment_json` is 30/30 unique triples (Westchester / Long Island duplicate blocks gone). FTA extract 2026-08-25. |
| **no_citable_chunk** | 42 | **resolved_layer_a** | Live segment rows now carry `source_location` (`Established Locations`). Committed rubric manifest still has `source_location: null`, so Layer B citation from the 276-claim packet remains null until the rubric is regenerated. |
| **not a prior claim-content failure** | 139 | n/a | unique_verbatim / location-disambiguated / boolean / composite — left un-reopened. |

**Status totals:** `resolved_relocation` 62 · `resolved_layer_a` 75 · `not_a_prior_failure` 139 · **persists 0** at the claim-id grain. Retired ids cited: 0. Broken placeholder cited: 0.

## 2. What remains (retriage, not claim-id persists)

1. **Residual vision-placeholder chunks** — `aee7745d…` and other "Five black, oval shapes" figures still sit on Pro Forma / P&L pages. Claim resolution remaps around them. Same class as closed `PB-fta_numeric-broken-chunk-repoint`; leftover is corpus hygiene, not a new claim-content miss.
2. **Stale rubric manifest** — `eval/content/fta_numeric_rubric_claims.json` still omits `source_location` on segment claims, so the presentation packet cannot resolve Layer B for those 75 even though Layer A is now citable.
3. **`prepare_spot_check` any-MVP-judge halt** — newly observed this run. Human `fta_numeric` prepare is blocked because a sibling surface is `judge`. Handed to T10 as candidate row text (not added here).

## 3. Recommendation for `PB-fta_numeric-post-m4-chunk-citation-drift`

`closes_when` is met by this re-run: persist-vs-resolve is documented per prior `claim_id`; remaining items are re-triaged as candidate text for T10. T9 does not write `product_backlog.yaml`.

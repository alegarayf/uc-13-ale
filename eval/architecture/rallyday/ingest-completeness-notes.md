Section:      ingest-completeness-notes
Version:      1.0.0
Last updated: 2026-08-19

Reference for separating **retrieval/eval weakness** from **ingest or corpus-shape confounds**. Sources: M4 ingestion-parser rollout closeout (`.dev/archive/M4_ROLLOUT_CLOSEOUT.md`, catalog `uc13_ale`, 2026-08-05–06) and CIM corpus probe (`.dev/archive/CIM_STATS_from_agent.md`).

## When to use

Before attributing low recall@k, S2 checklist misses, or sparse gold coverage to retrieval ranking or extraction:

- Confirm the company's corpus passed rollout gates (especially G3 sync, G4 join health, G5 attestation).
- Compare live chunk/embedding counts to the anchors below — large drift suggests incomplete ingest, catalog mismatch (`uc13` vs `uc13_ale`), or a partial Cell 7/8 run.
- Check company-specific coverage gaps (no CIM, classifier funnel, zero-chunk terminal docs) that limit what retrieval can ever return.

Related surfaces: `gold_labels ingestion_snapshot` contract and `_wait_for_index_sync` fail-closed behavior in `known-coupling-surfaces.md`; orphan/join failures in `failure-taxonomy.md` (R-08).

## M4 rollout gates (G0–G5)

Program-level proof points from the ingestion-parser refactor rollout. All four companies cleared with **0.000% orphan rate** on the doc_id join.

| Gate | Meaning | Verification |
|------|---------|--------------|
| **G0** | Governance: spec and charter pinned and approved before code runs | Spec header + approval fields (one recorded waiver on cycle-5 re-approval) |
| **G1** | Sync contract: vector-index sync halt/print behavior unchanged | `pytest tests/test_ingestion_parser_sync.py` |
| **G2** | Document-ID contract: `make_doc_id` normalizes paths identically forever | `pytest tests/test_make_doc_id.py` |
| **G3** | Fail-closed sync: run ends with `✓ Index ready` or halts with `✗ Sync failed — halting` | Live run output; never proceed on unconfirmed index |
| **G4** | Join health: orphan rate on chunks ↔ doc_relevance/doc_status join | Orphan-rate SQL per company (historical Elder Care baseline ~47.6% by filename; refactor target 0%) |
| **G5** | Attestation: every approved document in a terminal, explained state | Per-company `doc_status` counts: N approved, M COMPLETE, K FAILED with reason |

## Per-company corpus anchors (`uc13_ale`)

Measured at M4 rollout closeout unless noted. Chunks and embeddings are 1:1 for written rows.

| Company | Approved docs | COMPLETE / FAILED | Zero-chunk docs | Chunks + embeddings | Orphan rate (doc_id join) | Index sync |
|---------|---------------|-------------------|-----------------|---------------------|---------------------------|------------|
| Clearsulting | 22 | 22 / 0 | 0 | **2,417** | 0.000% | ✓ |
| GKF | 41 | 41 / 0 | 0 | **3,107** | 0.000% | ✓ |
| SPG | 364 | 358 / 0 | 6 | **43,602** | 0.000% | ✓ |
| Elder Care | 475 | 467 / 0 | 8 | **55,812** | 0.000% | ✓ |

**Catalog aggregate (2026-08-07):** 902 `doc_status` rows (888 COMPLETE, 14 ZERO_CHUNKS, 0 FAILED); vector index **104,938** rows, current.

### Coverage-shape caveats (not gate failures)

| Signal | Companies | Implication for eval |
|--------|-----------|----------------------|
| **No CIM on file** | SPG | No memorandum chunks — intents expecting CIM narrative will score weak regardless of retrieval tuning |
| **Classifier funnel** | Elder Care: 475 approved of **1,386** data-room files | Low scores may reflect `should_parse=false` tiering, not parser failure |
| **Coverage injection** | SPG: 391 distinct `doc_id`s in `chunks` vs 364 approved | Extra chunk docs injected per uncovered workstream — "approved ≠ parsed" by design |
| **Zero-chunk terminal docs** | Elder Care 8, SPG 6 | Explained empty extractions (ToS/contract Word, filtered `.xls`, one empty PDF) — not FAILED |
| **CIM-only chunk counts** | Clearsulting 941 · Elder Care 502 · GKF 473 · SPG none | CIM is a large share of Clearsulting/GKF/Elder Care text; SPG eval must not assume CIM coverage |

### CIM anchor (single-document subset)

| Company | CIM present | CIM chunks | CIM embeddings |
|---------|-------------|------------|----------------|
| Clearsulting | Yes (`Confidential Information Memorandum`) | 941 | 941 |
| Elder Care | Yes (`2024 Elder Care - CIM_vF.pdf`) | 502 | 502 |
| GKF | Yes (`Project Ajax CIM vF`) | 473 | 473 |
| SPG | **No** | — | — |

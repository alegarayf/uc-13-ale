# Ingestion parser rollout — closeout

**Program:** uc13-ingestion-parser M4 · **Catalog:** `uc13_ale` · **Closeout date:** 2026-08-07 · **Status:** complete (all four companies)

## What was rolled out

The per-document ingestion parser (parse → embed → sync) was force-rebuilt for every rollout company in `uc13_ale`. Each company run: re-stamp `doc_id` on `doc_relevance`, destructive `--force=company` re-parse, vector-index sync, and post-run checks. Rollout order was Clearsulting (pilot) → Elder Care (fire test) → GKF → SPG.

## Operator decisions

| Decision | Value |
|---|---|
| Catalog | `uc13_ale` |
| Compute | Agent-driven serverless `jobs.submit` (workspace policy rejects classic clusters) |
| Company order | Clearsulting pilot, then Elder Care, then GKF, then SPG |
| Destructive re-parse | Per-company `--force=company` approved |
| `doc_id` re-stamp | Approved — backfill NULL `doc_id` with `hash_catalog='uc13_ale'` to close M3 catalog-mismatch (pre-rollout chunk–doc join was 0% for Clearsulting/GKF/SPG; Elder Care 222/230) |
| Elder Care legacy cleanup | One-time scoped DELETE for pre-refactor `uc13`-hashed orphan chunks, then `sync_only` (only Elder Care needed this) |

## Environment notes (no code changes)

| Issue | Fix |
|---|---|
| Serverless rejected `doc_status` DDL with `DEFAULT FALSE` | Pre-created table via warehouse SQL with `TBLPROPERTIES('delta.feature.allowColumnDefaults'='supported')`; schema matches `status_store.ensure_doc_status` (14 columns) |
| Serverless missing runtime deps | Job env: `mlflow`, `openpyxl`, `python-docx`, `pymupdf>=1.24.0`, **`databricks-sdk==0.120.0` (pin required)** — newer SDK renames `VectorIndex.delta_sync_index_spec`, breaking index-sync introspection |

## Per-company results

| Company | Document status | Index sync | Chunk–doc join orphans | Notes |
|---|---|---|---|---|
| **Clearsulting** | 22 complete, 0 zero-chunk, 0 failed | Index ready; watermark 2026-08-05T16:30:49Z | 0.000% (2,417 chunks) | Pilot; validated restamp→parse→sync loop |
| **Elder Care** | 467 complete, 8 zero-chunk, 0 failed | Index ready; watermark 2026-08-05T22:42:46Z | 0.000% (55,812 chunks) | 4h timeout + resume verified; legacy orphan cleanup applied |
| **GKF** | 41 complete, 0 zero-chunk, 0 failed | Index ready; watermark 2026-08-06T16:07:32Z | 0.000% (3,107 chunks) | Single run, exit 0 |
| **SPG** | 358 complete, 6 zero-chunk, 0 failed | Index ready; watermark 2026-08-06T22:41:44Z | 0.000% (43,602 chunks) | Timeout + resume; 27 coverage-injected docs beyond approved set (by design) |

**Zero-chunk detail (content-driven, not parser defects):** Elder Care — 7× `ALL_CHUNKS_FILTERED`, 1× `EMPTY_EXTRACTION`; SPG — 6× `ALL_CHUNKS_FILTERED`.

## Catalog-wide closeout (measured 2026-08-07T13:01:05Z)

| Metric | Value |
|---|---|
| Total `doc_status` rows (four companies) | **902** |
| Complete | **888** |
| Zero-chunk | **14** |
| Failed | **0** |
| Non-terminal (pending/parsing/embedding) | **0** |
| Rows outside rollout companies | none |
| Final sync watermark | 2026-08-06T22:41:44Z |
| Index row count (catalog-wide, current) | 104,938 |

Per-company sums reconcile: 22 + 467 + 41 + 358 = 888 complete; 8 + 6 = 14 zero-chunk; 902 total. Source: shipped `eval/retrieval/measure_attestation.py` (see attestation signoff).

## Resumability and index readiness

Both Elder Care and SPG hit 4-hour serverless timeouts mid-run. Resume with `--force=none` reclassified stranded `PARSING` rows as `RETRY`, re-ran them idempotently (no duplicate chunks). Vector index reached **ready and current** for every company; SyncGate skip/trigger behavior verified on Clearsulting.

## Test suite at rollout close

```text
pytest tests/ eval/retrieval/tests/ -q
```

**872 passed, 5 skipped** at HEAD `e04f7b8` (2026-08-07).

## Related records

| Record | Path |
|---|---|
| Document status attestation (instrument + per-company lines) | [`signoffs/ingestion-parser-g5-attestation-2026-08-07.md`](ingestion-parser-g5-attestation-2026-08-07.md) |
| Changelog (rollout + audit remediation) | `CHANGELOG.MD` — sections `uc13-ingestion-parser / M4 — Operator rollout` and `M4 — Audit remediation` |
| Attestation tool | `eval/retrieval/measure_attestation.py` |

**Operator signature / date:** rollout attested in CHANGELOG 2026-08-05–07; tracked signoff committed 2026-08-18 (T-SIGNOFFS-INGESTION-PLAIN).

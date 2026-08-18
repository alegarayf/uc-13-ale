# Document status attestation — ingestion parser rollout

**Catalog:** `uc13_ale` · **Measured:** 2026-08-07T13:01:05Z · **Status:** attested via shipped tool

## What this attests

This record captures **document parsing outcomes** from `doc_status`: how many approved documents reached `COMPLETE`, how many ended in `ZERO_CHUNKS` (with reasons), and that no documents remain in non-terminal states. It is the post-rollout falsifier for “every approved document was processed to a terminal status.”

It does **not** by itself attest chunk-type composition — that is the separate **vision-share companion** query on the `chunks` table (text / table / vision counts). Both queries live in the same instrument and were run together for each company.

## Instrument and run evidence

| Field | Value |
|---|---|
| Module | `eval/retrieval/measure_attestation.py` |
| Execution path | CLI `_cli_main` → `build_parser` → `main` → Spark queries → formatter |
| Compute | Databricks serverless (`jobs.submit`) |
| Databricks run_id | `173344172853499` |
| Local run log (read-only, not committed) | `.dev/m4_attestation_run_log.txt` |
| Post-A1 formatter | Includes non-terminal status clause when present (none at measurement time) |

Audit remediation (A2) closed the gap where rollout numbers had come from an undeclared warehouse-SQL reimplementation (`.dev/m4_measure.py`). This attestation rests on the **orchestrator-owned artifact** above.

## Per-company attestation lines

Lines below are verbatim from the shipped tool output at measurement time.

| Company | Attestation line |
|---|---|
| **Clearsulting** | 22 approved, 22 complete |
| **Elder Care** | 475 approved, 467 complete, 8 failed with reason ALL_CHUNKS_FILTERED (7), EMPTY_EXTRACTION (1) |
| **GKF** | 41 approved, 41 complete |
| **SPG** | 364 approved, 358 complete, 6 failed with reason ALL_CHUNKS_FILTERED (6) |

“Failed” in the formatter means terminal **`ZERO_CHUNKS`** status (not `FAILED` with a hard error). All eight Elder Care and six SPG zero-chunk rows are accounted for in the reason breakdown.

## Catalog-wide reconciliation

| Status | Count |
|---|---|
| COMPLETE | **888** |
| ZERO_CHUNKS | **14** |
| FAILED | **0** |
| **Total rows** | **902** |

| Company | COMPLETE | ZERO_CHUNKS |
|---|---|---|
| Clearsulting | 22 | 0 |
| Elder Care | 467 | 8 |
| GKF | 41 | 0 |
| SPG | 358 | 6 |

No rows outside the four rollout companies. **Source:** F2 reconciliation block in `.dev/m4_attestation_run_log.txt`, matching CHANGELOG audit-remediation A2/A3.

Supersedes an earlier transcription error (“908 rows, 885 complete, 16 zero-chunk”) that did not reconcile arithmetically.

## Vision-share companion (informational)

Chunk counts by `source_type` from the same run — **not** a gate criterion, but recorded alongside attestation for operator visibility.

| Company | Text | Table | Vision | Total chunks |
|---|---|---|---|---|
| Clearsulting | 1,083 | 110 | 1,224 | 2,417 |
| Elder Care | 50,438 | 2,675 | 2,699 | 55,812 |
| GKF | 2,431 | 337 | 339 | 3,107 |
| SPG | 30,355 | 8,295 | 4,952 | 43,602 |

## Sync state at measurement

| Field | Value |
|---|---|
| `catalog_scope` | `uc13_ale` |
| `last_successful_sync` | 2026-08-06T22:41:44Z |
| Prior pipeline `run_id` | `e1e4f158-9e3d-4690-bd22-1beaf1b3c57d` |

## Related records

| Record | Path |
|---|---|
| Rollout closeout (index, orphans, operator decisions) | [`signoffs/ingestion-parser-rollout-2026-08-07.md`](ingestion-parser-rollout-2026-08-07.md) |
| Changelog A1–A4 | `CHANGELOG.MD` — `uc13-ingestion-parser / M4 — Audit remediation` |

**Operator signature / date:** attestation run 2026-08-07; tracked signoff committed 2026-08-18 (T-SIGNOFFS-INGESTION-PLAIN).

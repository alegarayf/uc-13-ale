# UC13 Ingestion Parser — Run Notes (Elder Care, Jul 2026)

Summary of log review and serverless failure pattern for Cell 7 (`ingestion_parser.main()`) in `databricks/jobs/notebooks/test_pipeline.ipynb`.

---

## Run context

| Setting | Value |
|---------|-------|
| Company | Elder Care |
| Files to parse | 382 |
| Vision endpoint | `databricks-claude-haiku-4-5` (figure extraction enabled) |
| Volume | `/Volumes/uc13_ale/ingestion/raw_files/Elder Care` |
| Runtime | ~3 hours on serverless before cluster health failure (observed twice) |

---

## Log review — did the parse itself fail?

**No.** The run did not fail as a whole. Per-file error handling kept processing after individual failures.

### Real errors (2 PDFs — 0 chunks each)

| File | Error |
|------|-------|
| `Plymouth [GL]_Lease_0324.pdf` | `UNRESOLVED_COLUMN` — column `content` cannot be resolved |
| `Stamford [Regus]_Lease_0324.pdf` | Same |

**Cause:** `read_files(..., format => 'binaryFile')` returned zero rows (`LocalRelation <empty>`), so Spark never had a `content` column for `ai_parse_document`. Likely causes: zero-byte/corrupt file, or `read_files` can't read the file even though `os.path.exists()` passed.

### Warnings (non-fatal)

- **Oversized chunks dropped** (5 visible) — Excel cells slightly over `MAX_CHUNK_CHARS` (7,500):
  - `Elder Care Projection Model Refresh_vF.xlsx` (1)
  - `Amex_Addbacks_0924-1224.xlsx` (1)
  - `CR Working_82000 Addbacks_0824.xlsx` (1)
  - `CR Working_82000 Addbacks_0922-0524.xlsx` (3)
- **openpyxl style warnings** (3×) — harmless; missing default workbook style on some Balance Sheet files.

### Thin output (parsed ✓ but empty)

| File | Result |
|------|--------|
| `L1 - Financial Addendum.docx` | 0 Word chunks |
| `L2 - Client Services Contract.docx` | 0 Word chunks |

### Other notes

- Duplicate filenames processed multiple times (expected if upload log has versions/duplicates).
- Log output was truncated (`max output size exceeded`) — final summary lines may be missing from captured output.
- Vast majority of files parsed successfully, including heavy vision workloads (CIM, tax returns, large Excel workbooks).

---

## Serverless cluster health failures

**"Execution failed due to cluster health" / "unhealthy cluster"** = Databricks killed the serverless session. This is infrastructure/preemption, not a normal Python exception from the parser.

### What Cell 7 does (single cell, no checkpoint)

1. Parse all approved files sequentially (vision = very slow)
2. Hold every chunk in driver memory (`all_chunks`)
3. Generate embeddings via BGE endpoint (batched API calls)
4. Write chunks + embeddings to Delta
5. Poll vector index sync (up to 30 min, `max_wait_seconds=1800`)

### Why ~3 hours + death fits

- Vision on Elder Care = thousands of LLM calls (CIM alone: 352 vision chunks)
- Everything runs in one Python process on the driver
- Serverless is prone to preemption on long, memory-heavy single cells
- The 2 failed lease PDFs are minor and would not kill the cluster

### Where it likely dies ("phase 1 → phase 2")

If failure happens after hours of `✓ file.pdf` lines, it's usually at the transition **after parsing ends**:

| Last output seen | Likely failure point |
|------------------|----------------------|
| Still printing `✓ somefile.pdf` | Parse phase — timeout/preemption |
| `=== Chunk diagnostics ===` | Memory spike at embed/write |
| `Generating embeddings...` | Embedding API or Delta write |
| `Vector search sync triggered` | Index sync polling (up to 30 min more) |

On success, stdout must include **`✓ Index ready`**. On fatal sync failure: **`✗ Sync failed — halting`** + `IndexSyncError`.

---

## Recommendations

### Immediate (reduce failure rate)

1. **Disable vision for first full rebuild** — clear `vision_endpoint` widget in Cell 1. Much faster, less driver load. Re-run with vision later if needed.
2. **Use a classic single-node cluster** for Cell 7, not serverless. More stable for 3+ hour jobs.
3. **Tier filter** — set `parse_priority_tiers` to `1` or `1,2` to shrink scope on first pass.

### If it keeps dying at the same spot after parse

Likely **driver OOM** from holding ~15k+ chunks + embeddings in memory before Delta write. Same mitigations apply (no vision, smaller tier scope, classic cluster with more driver memory).

### Coverage gaps to fix manually

- Re-ingest or inspect the 2 failed lease PDFs on the volume.
- `L1` / `L2` Word docs produced no chunks — verify source files aren't empty.

### Confirm a successful run

Scroll to end of Cell 7 output for:

```
=== Chunk diagnostics ===
✓ Saved N chunks → ...
Generated N embeddings
✓ Saved N embeddings → ...
✓ Index ready and current — ...
```

Do **not** proceed to Cell 8 / Phase 3 if `IndexSyncError` or cluster health failure occurred.

---

## Reference

- Parser script: `databricks/jobs/scripts/ingestion_parser.py`
- Notebook: `databricks/jobs/notebooks/test_pipeline.ipynb` (Cell 7)
- `MAX_CHUNK_CHARS = 7_500` — oversized chunks are dropped, not truncated

---

## Proposed refactor — incremental, resumable ingestion

The current design is a **dev notebook pattern**, not a production-ready ingestion model. It should be refactored before relying on it in prod or for PHV e2e gates (T6 M3).

### Problem with current design

Cell 7 behaves as one big transaction:

1. Parse all approved files into a giant `all_chunks` list on the driver
2. Embed everything in memory
3. Write Delta tables
4. Sync the vector index

`ensure_coverage.py` only helps *after* a successful full run — it fills gaps but does not make the main path resumable.

**Why this breaks:**

- ~3 hours of work with zero checkpoint → PHV e2e is all-or-nothing
- Serverless death at hour 2.5 → start over from scratch
- Memory spikes at the parse → embed handoff
- Per-file failures are handled, but there is no durable record of what is *done* vs *pending* without re-running

### Target shape

Process one document at a time; write incrementally with idempotency:

```
for each approved doc:
  if already ingested (and not --force): skip
  parse → write chunks → embed → write embeddings → mark complete
optional: trigger index sync once at end (or per batch)
```

### Idempotency

Building blocks already partially exist:

| Key | Use |
|-----|-----|
| `doc_id` / `make_doc_id(file_path)` | Natural per-document identifier |
| Company + file_name + file mtime/hash | Detect source changes |
| **Ingestion status table** | `doc_id`, `status`, `chunk_count`, `ingested_at`, `error` — turns crashes into "resume from pending/failed" |

### `--force` vs default behavior

| Mode | Behavior |
|------|----------|
| **Default (prod / PHV)** | Incremental, resumable; skip `COMPLETE` docs unless source changed |
| **`--force` (dev)** | Current behavior — delete company's rows, re-parse everything. Keep it, but not as the only path |

### Index sync

Syncing after every doc is too slow. Reasonable options:

- Sync once at end of a run
- Sync every N docs (batch)
- `--skip-sync` for mid-run retries so a crash during sync does not force a full re-parse

### PHV / e2e testing angle

T6 M3 PHV should prove the pipeline works end-to-end, not that one notebook cell survives 3 hours on serverless. Resumable ingestion enables:

- Partial runs still leave queryable chunks/embeddings
- Re-run only failed docs and still hit the exit gate (`✓ Index ready`)
- Failures become attestable: *"382 files, 380 complete, 2 failed with reason X"* instead of *"cluster died, unknown state"*

The Elder Care logs support this — most files succeed, a few fail, and the platform kills the run late. **"380 done, resume 2"** beats **"run 3 hours again."**

### `ensure_coverage` is not a substitute

It is a gap-filler assuming the main parser already succeeded. The main parser needs to *be* incremental.

### Suggested migration path

1. **Status table + per-doc write loop** — biggest win, smallest conceptual change
2. **Move embedding inside the per-doc loop** (or small batches of docs)
3. **Keep full-rebuild as `--force`**
4. **Later:** per-doc job tasks if parallelism is needed

### Open design choices (for spec / charter)

- Index sync granularity (per doc vs batch vs end-only)
- Whether failed docs auto-retry
- Whether `--force` is per-company or per-doc

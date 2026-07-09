# UC13 Databricks Pipeline — Developer Context

## What this project is

A private equity diligence pipeline running entirely on Databricks. It ingests a company's data room documents (PDFs, Excel, Word, CSV) from SharePoint, parses them into searchable chunks, and runs a set of workstream agents that extract structured diligence outputs (business model, financial trends, customer quality, KPIs, legal contracts, quality of earnings).

The client spec is in `Guidelines/Austin_email_guidelines.txt`. The build specification is in `Guidelines/` (a PDF and a TXT). Read these before proposing structural changes.

---

## Repository layout

```
databricks/
  jobs/
    scripts/            # All production scripts — each has a main() callable from notebook or job
      ingestion_parser.py     # Phase 2b: PDF/Excel/Word/CSV → chunks + embeddings
      ensure_coverage.py      # Phase 2c: incremental APPEND-only gap filler (never deletes)
      document_classifier.py  # Phase 2a: LLM assigns workstream tags + priority tier
      download_upload.py      # Phase 1:  SharePoint → UC Volume
      company_profiler.py     # Phase 2b: structured company profile (overlay detection)
      setup_vector_search.py  # One-time: creates VS endpoint + index
    notebooks/
      test_pipeline.ipynb     # End-to-end test notebook — always adapt this when scripts change
  agents/
    shared/
      retrieval.py        # semantic_search() — used by all Phase 3 agents
      agent_base.py       # WorkstreamAgent base class + tool-call/trace infrastructure
    workstreams/          # Phase 3 agents — one file per diligence workstream
      business_model_agent.py
      financial_trends_agent.py
      customer_quality_agent.py
      kpi_agent.py
      legal_contracts_agent.py
      quality_of_earnings_agent.py
    ingestion/
      tools/connector.py  # SharePoint connector (list_companies, download files)
  workflows/              # Databricks Workflow YAML definitions
  Guidelines/             # Client spec (Austin email) + build spec PDF
  context_docs/           # Reference documents (not committed, used locally)
```

---

## Delta table catalog

Unity Catalog: **`uc13`**

| Table | Written by | Purpose |
|---|---|---|
| `uc13.ingestion.upload_log` | `download_upload.py` | Files downloaded from SharePoint |
| `uc13.classification.doc_relevance` | `document_classifier.py` | Workstream tags, priority tier, should_parse flag |
| `uc13.ingestion.chunks` | `ingestion_parser.py` | Text chunks with section_header, page_start, source_type |
| `uc13.ingestion.embeddings` | `ingestion_parser.py` | BGE vectors + workstream + priority_tier + source_type |
| `uc13.classification.company_profile` | `company_profiler.py` | Industry overlay, revenue model, deal type |
| `uc13.analysis.business_model` | `business_model_agent.py` | Structured business model output |
| `uc13.analysis.financial_trends` | `financial_trends_agent.py` | Revenue/margin/EBITDA trends |
| `uc13.analysis.customer_quality` | `customer_quality_agent.py` | Concentration, NRR/GRR, contract triggers |
| `uc13.analysis.kpi` | `kpi_agent.py` | Overlay-specific KPIs |
| `uc13.analysis.legal` | `legal_contracts_agent.py` | Contract register, CoC, litigation — **M0 write target** (21-column Appendix A DDL) |
| `uc13.analysis.legal_contracts` | — (compat VIEW) | Legacy consumers; subset of `analysis.legal` + `triggered_reviews_loaded=0` |
| `uc13.analysis.quality_of_earnings` | `quality_of_earnings_agent.py` | Addback ledger, EBITDA scenarios |

Vector Search index: **`uc13.ingestion.embeddings_index`** (Delta Sync, auto-updated)

---

## Key design rules

### Ingestion — two modes, never mix them

- **`ingestion_parser.py main()`**: DELETE all rows for the company → parse all approved files → APPEND fresh. Idempotent full rebuild. Use when extraction logic changes.
- **`ensure_coverage.py ingest_missing()`**: APPEND only, never deletes. Use when a workstream is missing files after the main parse. Always check with `get_coverage_report()` first (Cell 8c), then fill with `ingest_missing()` (Cell 8d).

### `source_type` column

Every chunk and embedding row carries `source_type`:
- `"text"` — prose extracted by `ai_parse_document`
- `"table"` — HTML table converted to markdown via `_html_table_to_markdown()`
- `"vision"` — chart/org-chart page rendered by PyMuPDF + vision LLM

When adding new source types, update: `Chunk` dataclass, `main()` DDL and schema in `ingestion_parser.py`, same schema in `ensure_coverage.py`, and `retrieval.py` SELECT clauses.

### Excel workbooks — merged cells

Load Excel files with `read_only=False, data_only=True`. **Never use `read_only=True`** for financial sheets — it disables the `.merged_cells` attribute, so non-top-left cells of merged header ranges return `None` and column headers are lost. Call `_expand_merged_cells(ws)` on each worksheet before row iteration; it copies the top-left value to every cell in each merge range and then unmerges, making all cells visible to the row iterator.

### PDF vision extraction — financial sections

Sparse-page detection in `parse_pdf()` automatically flags pages inside a financial section (matched by `_FINANCIAL_SHEET_RE` against section headers) that have fewer than 30 text characters. These pages are added to `figure_page_header_map` so the vision LLM processes them even when `ai_parse_document` returns no `figure` elements. The vision loop selects `_VISION_PROMPT_FINANCIAL` (column-aligned tabular output) instead of the generic `_VISION_PROMPT` when the section header matches the financial regex. Vision `max_tokens` is 2,000 for financial pages.

### `semantic_search()` — source-type parameters

`retrieval.py:semantic_search()` accepts two optional parameters added for financial retrieval:
- `source_type_priority=True` — sorts table/vision chunks before text chunks within each priority tier. Use for financial queries where structured chunks carry denser data per character than prose.
- `source_type_filter=["table","vision"]` — restricts results to specific source types. Applied after all other filters, before the `top_k` cap.

### `_call_llm()` — max_tokens override

The base class default is `max_tokens=12_000`. Agents with especially large extraction schemas (e.g. `financial_trends_agent.py`, which uses a 10-array schema) should pass an explicit override: `self._call_llm(..., max_tokens=16_000)`. The assessment narrative LLM call is a separate invocation and has its own `max_tokens` (6,000). Never rely on the default for production agents — set it explicitly in each `_call_llm()` call so truncation budget is visible at the call site.

### Schema changes in analysis tables

Each Phase 3 agent's `main()` contains an `_EXPECTED_COLS` guard that auto-detects schema drift and drops + recreates the table before writing. **Do not add a separate migration cell to the notebook** — the guard in `main()` is the single source of truth. Always keep `_EXPECTED_COLS` in the agent synchronized with the actual `StructType` schema used for the write.

### `mergeSchema=True` on all Delta writes

All `df.write` calls in `ingestion_parser.py` and `ensure_coverage.py` use `.option("mergeSchema", "true")`. This allows adding new columns (like `source_type`) to existing tables without a manual `ALTER TABLE`. Do not remove this option.

### `get_param()` / `get_secret()` pattern

All scripts use a dual-source helper: tries `dbutils.widgets.get()` first, falls back to `os.environ`. **Always mirror widget values into `os.environ` in Cell 1 of the notebook** so scripts imported as modules (where `dbutils` is not a direct global) can still read them. Never use `dbutils.widgets.get()` directly inside a script module.

## Catalog convention

Two Unity Catalog names appear across the pipeline; they are **not** interchangeable:

| Catalog | Role |
|---|---|
| **`uc13`** | Production catalog — all `main()` entry points in `databricks/jobs/scripts/` and `databricks/agents/workstreams/` must default to this via `get_param("catalog", default="uc13")`. |
| **`uc13_ale`** | Eval / harness / PHV-validation catalog — used by `test_pipeline.ipynb` Cell 1 (`dbutils.widgets.text("catalog", "uc13_ale")`), workflow YAML parameter defaults, and eval/QA instrumentation. |

**Resolution path:** every production script reads the active catalog through `get_param("catalog", default="uc13")`, which tries the Databricks widget first and falls back to `os.environ["catalog"]`. The notebook's Cell 1 must mirror the widget value into `os.environ` (see `get_param()` / `get_secret()` pattern above) so module imports resolve the same catalog the operator set in the UI.

**Enforcement:** `tests/test_catalog_convention.py` (item 22, §5.12.3) statically scans the production-safe layer for correct `get_param` defaults, notebook widget pins, and bypass literals or shadow constants. That test is the authoritative compliance gate — this section documents the convention only; it does not assert per-file compliance status.

---

## Endpoint names (Databricks model serving)

| Role | Endpoint name | Widget |
|---|---|---|
| Embeddings | `databricks-bge-large-en` | `embedding_endpoint` |
| Extraction LLM (structured JSON — Haiku for speed; Sonnet via `llm_endpoint` for narrative) | `databricks-claude-haiku-4-5` | `extraction_endpoint` |
| Narrative LLM (assessment reports) | `databricks-claude-sonnet-4-6` | `llm_endpoint` |
| Vision LLM (optional, figure pages) | `databricks-claude-haiku-4-5` | `vision_endpoint` |

**Two-LLM pattern:** FTA uses `extraction_endpoint` (Sonnet) for the single big structured-JSON call (`max_tokens=12_000`, ~90-150s) and `llm_endpoint` (Sonnet) for narrative assessment calls (Cells 11c/12b). BMA uses `extraction_endpoint` for its extraction call and `llm_endpoint` for the narrative. The orchestrator reads from the Delta table, which is written from extraction output only. **Hard token caps on this workspace:** Llama 3.3 70B is capped at 8,192 output tokens; Claude Haiku 4.5 is also capped at 8,192 output tokens (requests for higher are silently floored). Only Sonnet 4.6 reliably generates 10-16K tokens. Do not use Haiku for extraction schemas that exceed ~6,000 tokens of output.

Vision extraction is opt-in: set the `vision_endpoint` widget in Cell 1 to enable. Leave blank to skip (no PyMuPDF dependency, faster parse).

---

## Testing workflow (test_pipeline.ipynb)

Always run cells in this order after code changes:

1. **Cell 0** — `%pip install` (once per cluster restart; includes `pymupdf>=1.24.0`)
2. **Cell 1** — Config widgets + `os.environ` sync. Set `vision_endpoint` to `databricks-claude-haiku-4-5` if image-based P&L extraction is needed (CIM pages 45+). `llm_endpoint` defaults to `databricks-claude-sonnet-4-6`.
3. **Cell 7** — Ingestion Parser (`s3.main()`) — full rebuild of chunks + embeddings. **Required after any change to `ingestion_parser.py`** (including the Excel merged-cell fix). Existing chunks do not update automatically.
4. **Cell 8** — Verify chunk stats + `source_type` distribution + PDF coverage flags
5. **Cell 8e** — Vision chunk spot-check (if `vision_endpoint` was set)
6. **Cell 8c** — Coverage diagnostic (read-only): confirms all workstreams have ≥1 ingested file
7. **Cell 8d** — Incremental ingest (only if Cell 8c shows "NO COVERAGE" for any workstream)
8. **Cell 11** — Business Model Agent (runs `bma.main()`, schema migration guard runs automatically)
9. **Cell 11b** — Inspect rich structured fields from the agent result
10. **Cell 12** (or equivalent) — Financial Trends Agent (`fta.main()`). Runs 8 retrieval tools: financial statements, EBITDA/margins, revenue by segment, working capital, addback schedule, company profile, revenue by geography, projected financials.

When changing a Phase 3 agent's schema, just re-run the agent cell — the `_EXPECTED_COLS` guard drops and recreates the table automatically. No separate migration step.

### M-PHV1 exit-gate verification (item 8)

Operator-run checkpoint for the index-sync fail-closed fix (O-07/P-06). This runbook documents how to confirm the behavior on a live Databricks cluster. **It is not executed automatically** — run these steps manually after the prerequisite below passes.

#### Prerequisite — unit tests green

Before attempting any cluster run, confirm the static contract is satisfied locally:

```bash
pytest tests/test_ingestion_parser_sync.py -v
```

All 9 tests must pass. They prove `IndexSyncError` propagates through `ingestion_parser.main()` (Cell 7 path) and `ensure_coverage.ingest_missing()` (Cell 8d path) on terminal `FAILED`/`CANCELED` states, on timeout (`max_wait_seconds` exceeded), and that the success path emits the required stdout substring. The timeout path is impractical to reproduce on-cluster (default `max_wait_seconds=1800`); treat the unit test `test_wait_for_index_sync_raises_on_timeout` as authoritative for that path.

#### Observable stdout contract

These substrings are binding — verify them against Cell 7 or Cell 8d output, not paraphrased:

| Path | Required stdout substring | Exception |
|---|---|---|
| Success | `✓ Index ready` (e.g. `✓ Index ready and current — uc13.ingestion.embeddings_index`) | None — cell completes normally |
| Terminal `FAILED`/`CANCELED` | `✗ Sync failed — halting` | Uncaught `IndexSyncError` |
| Timeout (`elapsed >= max_wait_seconds`) | `✗ Sync failed — halting` | Uncaught `IndexSyncError` |
| Outer sync error (permissions, API failure, etc.) | `✗ Sync failed — halting` | Uncaught `IndexSyncError` |

On fatal paths, **do not proceed** to Cell 8 verification, Cells 8c–8d, or any Phase 3 agent cells. The notebook markdown at Cell 7 and Phase 3 Pre-flight documents the same halt-on-failure rule.

> **Open question (confirm on first real run):** Databricks Jobs / notebook execution is assumed to treat an uncaught `IndexSyncError` as a non-zero cell exit without an explicit `sys.exit()`. If your runner reports success despite the exception appearing in stdout, the exit-gate check is insufficient — escalate via the charter amendment path (see below), do not reinterpret the gate as passed.

#### (b) Success path — normal Elder Care parse

1. Attach cluster, run **Cell 0** (`%pip install`) then **Cell 1** (config). Confirm `sp_company_name` is `Elder Care` and `llm_endpoint` is `databricks-claude-sonnet-4-6` (defaults — no change expected).
2. Run prerequisite cells through Phase 2a if data is not already loaded (Cells 2–6 as needed for your workspace state).
3. Run **Cell 7** (`s3.main()` — full ingestion rebuild).
4. **Pass criteria:**
   - Cell completes without `IndexSyncError`.
   - Stdout contains `✓ Index ready` near the end of the sync polling block.
   - **Cell 8** runs and shows expected chunk/embedding counts for Elder Care.
   - Phase 3 cells (e.g. **Cell 11** Business Model Agent) can proceed without retrieval returning 0 chunks due to a stale index.

#### (a) Simulated-failure path — confirm halt on fatal sync

Goal: prove Cell 7 stops the notebook on a fatal sync path with the exact stdout substring and an uncaught `IndexSyncError`.

**Terminal state (`FAILED` or `CANCELED`) — recommended cluster procedure:**

1. Complete steps 1–2 from the success path above.
2. Start **Cell 7** and let parsing finish so index sync begins (you should see `Vector search sync triggered → uc13.ingestion.embeddings_index` and polling lines).
3. While polling is active, open **Workflows → Delta Live Tables** (or Pipelines) in the Databricks UI. Locate the DLT pipeline ID printed in Cell 7 output (`DLT pipeline : <id>`).
4. **Cancel** that pipeline update (or let a known-broken test pipeline reach `FAILED` if you maintain a dedicated test index).
5. **Pass criteria:**
   - Cell 7 stdout includes `✗ Sync failed — halting` (with pipeline state `FAILED` or `CANCELED` in the message).
   - Cell 7 terminates with an uncaught `IndexSyncError` (red error in notebook UI; cell status failed).
   - Downstream cells were **not** run — operator confirms Phase 3 was not attempted on an unconfirmed index.

**Cell 8d (optional, if coverage gap exists):** Repeat the same cancel-during-sync procedure while running **Cell 8d** (`ec.ingest_missing()`). Expect the same `✗ Sync failed — halting` + uncaught `IndexSyncError` — this replaces the prior warn-and-continue behavior.

**Timeout path:** Do not wait 30 minutes on-cluster. Rely on `test_wait_for_index_sync_raises_on_timeout` from the prerequisite step.

**Outer-exception path:** Hard to trigger reliably on-cluster without infrastructure changes. The unit tests cover the `IndexSyncError` re-raise contract; if you observe this path live, confirm `✗ Sync failed — halting` appears before the exception.

#### Mismatch handling

If observed cluster behavior diverges from this runbook (missing stdout substrings, exception swallowed, job reports success despite `IndexSyncError`, or DLT states other than `FAILED`/`CANCELED` that should halt), **do not silently reinterpret the exit gate as passed**. Re-open the underlying fix via the charter's amendment path (`.dev/specs/pipeline/uc13_pipeline_hardening_milestone_charter.md` §7 escalation ladder). This runbook was derived from static code reading and unit tests, not from an automated cluster execution in CI.

**Out of scope for this checkpoint:** deploying or exercising `uc13_ingestion_pipeline.yml` (M-PHV3). Notebook-only operator discipline is the current enforcement mechanism.

---

## Databricks-specific constraints

- **Volume paths** use `/Volumes/{catalog}/{schema}/raw_files/{company}/` — treat these as regular filesystem paths (they are FUSE-mounted). `os.path.exists()` and `open()` work.
- **`dbutils`** is only available as a direct global inside notebook cells. Inside imported modules, use `_get_dbutils()` (the helper that falls back to `IPython.get_ipython().user_ns`).
- **SparkSession**: always use `SparkSession.getActiveSession()` inside scripts — never create a new session.
- **`ai_parse_document`**: Databricks SQL function (version 2.0). Returns elements with types: `title`, `section_header`, `text`, `table` (HTML content), `figure` (empty content for images/charts), `page_footer`, `page_number`. Table content is raw HTML — always use `_html_table_to_markdown()`, never `_strip_html()` on table elements.
- **Vector Search**: use `WorkspaceClient().vector_search_indexes.query_index()`. The `retrieval.py` fallback uses keyword LIKE search when VS fails.
- **`%pip install`** in notebooks restarts Python — Cell 1 (Config) must always be re-run after Cell 0.

---

## Industry overlays

The company profiler detects one of: `healthcare`, `tech_services`, `b2b_saas`, `industrial`, `consumer`. Overlay-specific fields in the business model output are nested under `customer_profile_json → overlay_specific → {healthcare|tech_services|b2b_saas}`. Completeness checks in the agent are gated on the confirmed overlay — do not add overlay-specific logic to the base extraction path.

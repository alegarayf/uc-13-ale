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
| `uc13.analysis.legal_contracts` | `legal_contracts_agent.py` | Contract register, CoC, litigation |
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

---

## Endpoint names (Databricks model serving)

| Role | Endpoint name |
|---|---|
| Embeddings | `databricks-bge-large-en` |
| Main LLM | `databricks-meta-llama-3-3-70b-instruct` |
| Vision LLM (optional) | `databricks-meta-llama-3-2-11b-vision-instruct` |

Vision extraction is opt-in: set the `vision_endpoint` widget in Cell 1 to enable. Leave blank to skip (no PyMuPDF dependency, faster parse).

---

## Testing workflow (test_pipeline.ipynb)

Always run cells in this order after code changes:

1. **Cell 0** — `%pip install` (once per cluster restart; includes `pymupdf>=1.24.0`)
2. **Cell 1** — Config widgets + `os.environ` sync. Set `vision_endpoint` to `databricks-meta-llama-3-2-11b-vision-instruct` if image-based P&L extraction is needed (CIM pages 45+).
3. **Cell 7** — Ingestion Parser (`s3.main()`) — full rebuild of chunks + embeddings. **Required after any change to `ingestion_parser.py`** (including the Excel merged-cell fix). Existing chunks do not update automatically.
4. **Cell 8** — Verify chunk stats + `source_type` distribution + PDF coverage flags
5. **Cell 8e** — Vision chunk spot-check (if `vision_endpoint` was set)
6. **Cell 8c** — Coverage diagnostic (read-only): confirms all workstreams have ≥1 ingested file
7. **Cell 8d** — Incremental ingest (only if Cell 8c shows "NO COVERAGE" for any workstream)
8. **Cell 11** — Business Model Agent (runs `bma.main()`, schema migration guard runs automatically)
9. **Cell 11b** — Inspect rich structured fields from the agent result
10. **Cell 12** (or equivalent) — Financial Trends Agent (`fta.main()`). Runs 8 retrieval tools: financial statements, EBITDA/margins, revenue by segment, working capital, addback schedule, company profile, revenue by geography, projected financials.

When changing a Phase 3 agent's schema, just re-run the agent cell — the `_EXPECTED_COLS` guard drops and recreates the table automatically. No separate migration step.

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

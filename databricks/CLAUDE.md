# UC13 Databricks Pipeline — Developer Context

> **Cursor agents:** live workspace access from the laptop is documented in repo-root [`AGENTS.md`](../AGENTS.md) and the [`databricks-access`](../.cursor/skills/databricks-access/SKILL.md) skill. This file covers pipeline implementation only.

## What this project is

A private equity diligence pipeline running entirely on Databricks. It ingests a company's data room documents (PDFs, Excel, Word, CSV) from SharePoint, parses them into searchable chunks, and runs a set of workstream agents that extract structured diligence outputs (business model, financial trends, customer quality, KPIs, legal contracts, quality of earnings).

The client spec is in `Guidelines/Austin_email_guidelines.txt`. Business-type overlay guidelines are in `Guidelines/Austin_guidelines_bussines_type.txt`. The build specification is in `Guidelines/` (a PDF and TXT files). Read these before proposing structural changes.

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
      md_to_word.py               # Converts PE diligence markdown reports to styled .docx (python-docx)
      run_ingestion_pipeline.py   # Phase 1-2 runner: download → classify → parse (tiers 1&2) → coverage_backfill → profile (sequential)
      run_diligence_pipeline.py   # Phase 3-5 runner: delegates to PipelineOrchestrator DAG
      run_full_pipeline.py        # Phase 1-5 end-to-end runner: calls run_ingestion_pipeline() then run_pipeline()
      run_vdr_pipeline.py         # VDR wrapper: reads companies_vdr_history row → run_full_pipeline() → copies docx to VDR volume → updates record
    notebooks/
      test_pipeline.ipynb           # End-to-end test notebook — adapt when scripts change
      run_vdr_job.py                # notebook_task entry for the VDR job: reads table_name/record_id widgets → run_vdr_pipeline()
      00_setup_vector_search.ipynb  # One-time VS endpoint + index setup
      01_document_classifier.ipynb  # Phase 2a: classify + tag documents
      02_ingestion_parser.ipynb     # Phase 2b: parse → chunks + embeddings
      03_company_profiler.ipynb     # Phase 2b: build company profile overlay
    sql/
      create_rules_table.sql                  # garden.garden_rules DDL
      alter_rules_table_to_ai_schema.sql      # Adds AI schema columns (nl_prompt, etc.)
      alter_sourcing_criteria_add_user_id.sql # Adds user_id to sourcing criteria table
      seed_rules.sql                          # Seed data for garden_rules
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
      forecast_agent.py             # Phase 3: forecast assumption credibility + downside sensitivities
      cross_analysis_agent.py       # Phase 4: cross-workstream reconciliation + top-10 issues
    orchestration/
      pipeline.py                   # PipelineOrchestrator: Phase 3→5 DAG, parallelism, retry, failure isolation, run manifest; to_result_card()
      orchestrator_agent.py         # Phase 5: assembles final diligence memo (.md + .docx)
    exec_summary/                   # (Ale) Bundle/report layer: BundleBuilder, tldr_compress, Rev3 one-pager; build_exec_summary() is the VDR bridge
    subagents/
      workstream/
        financial/        # Parallel sub-agents for FinancialTrendsAgent (see section below)
          revenue_sub_agent.py   # Revenue, gross margin, revenue_by_segment/geography
          ebitda_sub_agent.py    # EBITDA versions, addback schedule, working capital
          opex_sub_agent.py      # OPEX breakdown, cost structure, executive summary
          context_utils.py       # build_focused_context(), semantic_search_with_fallback()
          shared_prompts.py      # SYSTEM_PROMPT_BASE + SYSTEM_PROMPT_EBITDA
    ingestion/
      tools/
        connector.py  # SharePoint connector (list_companies, download files)
        uploader.py   # UC Volume uploader — LOCAL (REST API) and DATABRICKS (pathlib) modes
  workflows/              # Databricks Workflow YAML definitions
    uc13_ingestion_pipeline.yml  # Phase 1-2 job (multi-task, individual script per task)
    uc13_diligence_pipeline.yml  # Phase 3-5 job (single task → PipelineOrchestrator DAG)
    uc13_full_pipeline.yml       # Phase 1-5 end-to-end job (2 tasks: ingestion → diligence)
    vdr_pipeline.yml             # UI-triggered VDR job (notebook_task, no params; reads companies_vdr_history)
  Guidelines/             # Client spec (Austin email, business type guidelines) + build spec PDF
  context_docs/
    architecture/         # UC13 pipeline architecture docs (HTML + Markdown)
    example_report.md     # Sample PE diligence output report
```

---

## Financial Trends parallel sub-agents

`financial_trends_agent.py` now delegates extraction to three autonomous sub-agents that run in parallel, replacing the former single-LLM call over a 60K-char shared context.

| Sub-agent | File | Retrieval queries | Max context | Max tokens | Fields extracted |
|---|---|---|---|---|---|
| `RevenueSubAgent` | `revenue_sub_agent.py` | 5 (financial_statements, revenue_by_segment, revenue_by_geography, customer_revenue, quickbooks_pl) | 25K chars | 10,000 | revenue_trend, gross_margin, revenue_by_segment, revenue_by_customer |
| `EbitdaSubAgent` | `ebitda_sub_agent.py` | 4 (financial_statements EBITDA rows, ebitda_and_margins, working_capital, addback_schedule) | 22K chars | 8,000 | ebitda (≤3 versions), addback_schedule, working_capital, budget_vs_actual, discrepancies_found |
| `OpexSubAgent` | `opex_sub_agent.py` | 3 (financial_statements OPEX rows, working_capital, projected_financials) | 15K chars | 3,000 | opex_breakdown, cost_structure, executive_summary, extraction_notes |

### EBITDA version cap (3 max)

`EbitdaSubAgent` extracts at most 3 EBITDA version types: `reported`, `pf_adjusted`, and `clinic_level_adjusted`. Intermediate adjusted concepts (diligence adjusted, normalized, partial adjustment) are skipped when a `pf_adjusted` version is also present. A document with 10 periods and 3 version types produces at most 30 records.

### `build_focused_context()` — CIM-first, source-type-aware

`context_utils.py:build_focused_context()` deduplicates chunks, then sorts by tier priority: CIM documents → Priority Tier 1 → other. Within each tier, table/vision chunks precede text. Per-chunk character limits vary by tier and source type (CIM structured: 4,000; CIM text: 2,500; PT1 structured: 3,000; PT1 text: 1,000; other: 500–1,000). Returns `(context_text, stats_str)`.

### `semantic_search_with_fallback()`

`context_utils.py:semantic_search_with_fallback()` wraps `retrieval.py:semantic_search()` with an automatic retry: if results with `file_name_filter` fall below `min_results`, it retries without the filter so non-standard filenames are not silently excluded.

### System prompts — two variants

- `SYSTEM_PROMPT_BASE` (rules 1–10): used by Revenue and Opex sub-agents. Covers extraction discipline, citation requirements, margin/growth layout rules, and period label rules.
- `SYSTEM_PROMPT_EBITDA` (rules 1–13): extends BASE with EBITDA-specific rules — multiple named EBITDA lines, addback table extraction, and the 3-version cap.

---

## `uploader.py` — UC Volume file uploader

`agents/ingestion/tools/uploader.py` accepts `FilePayload` objects (raw bytes + metadata) and writes them to a UC Volume, preserving folder structure. It switches transparently between two modes:

- **LOCAL** — uploads via Databricks Files REST API using a PAT (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `UC_VOLUME_PATH`, `SP_COMPANY_NAME` env vars required)
- **DATABRICKS** — writes directly to the Volume filesystem path using `pathlib`

Does not do parsing, Delta table writes, SharePoint/connector logic, or credential management beyond reading env vars.

---

## `md_to_word.py` — Markdown → styled Word export

`jobs/scripts/md_to_word.py` converts PE diligence markdown assessments (Financial Trends and Business Model report formats) to `.docx` using `python-docx`. Applies a branded color palette (navy, blue, red/yellow flag rows). Callable from a notebook cell or as a standalone script:

```python
from jobs.scripts.md_to_word import convert_md_to_word
convert_md_to_word(
    md_path  = "/Volumes/uc13/analysis/reports/Elder_Care/financial_trends_report.md",
    out_path = "/Volumes/uc13/analysis/reports/Elder_Care/financial_trends_report.docx",
)
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
| `uc13.analysis.forecast` | `forecast_agent.py` | Assumption credibility (Supported/Plausible/Stretch), revenue build vs trailing, downside sensitivities |
| `uc13.analysis.cross_analysis` | `cross_analysis_agent.py` | Reconciliation log, CIM-claims vs data-room, top-10 issues, gap list |
| `uc13.analysis.diligence_report` | `orchestration/orchestrator_agent.py` | Final memo metadata + coherence log + agent run manifest; artifacts at `/Volumes/uc13/analysis/reports/{company}/final_diligence_memo.{md,docx}` |

Vector Search index: **`uc13.ingestion.embeddings_index`** (Delta Sync).

- **`columns_to_sync` must include the metadata columns** (`company_name`, `workstream`, `priority_tier`, `source_type`, `file_name`, `chunk_id`, `doc_id`) or filter **pushdown fails** ("Columns referenced in filters are not present in index") and `semantic_search` silently falls back to unfiltered retrieval + post-filter → poor recall and cross-company bleed. `setup_vector_search.py` already lists them.
- **A pre-existing index is NOT auto-updated** — `setup_vector_search` is idempotent and skips an existing index, so an index created by older code keeps its old (metadata-less) sync spec. To change synced columns you must **drop + recreate** the index and re-sync (~181K rows), then re-run.

**`uc13.ops` schema (RE² provenance store) — hard prerequisite.** `pipeline.py` sets `RE2_STORE_BACKEND=delta`, so every agent's retrieval writes provenance to `{catalog}.ops.retrieval_harness_runs`. If the `ops` schema/tables don't exist in the catalog, **all agents crash** with `TABLE_OR_VIEW_NOT_FOUND`. Create them once per catalog with `eval/retrieval/scripts/apply_ops_ddl.sql` (`{catalog}`→ target; additive `IF NOT EXISTS`). This is separate from `setup_vector_search` and must be run for any new catalog.

---

## Pipeline orchestration (Phase 1 → 5)

### Three entry points — choose by what needs to run

| Entry point | Phases | When to use |
|---|---|---|
| `run_ingestion_pipeline.py` | 1-2 | New data room files added; re-run classification or parsing |
| `run_diligence_pipeline.py` | 3-5 | Embeddings already populated; re-running or debugging diligence agents |
| `run_full_pipeline.py` | 1-5 | New company (first-time run) or full refresh |

### Databricks jobs

| Job YAML | Tasks | Entry point |
|---|---|---|
| `uc13_ingestion_pipeline.yml` | 1 per script (multi-task, existing) | Individual Phase 1-2 scripts |
| `uc13_diligence_pipeline.yml` | 1 task (single-task) | `run_diligence_pipeline.py` |
| `uc13_full_pipeline.yml` | 2 tasks: `ingestion_pipeline` → `diligence_pipeline` | `run_ingestion_pipeline.py` then `run_diligence_pipeline.py` |
| `vdr_pipeline.yml` | 1 `notebook_task` (serverless env) | `jobs/notebooks/run_vdr_job` → `run_vdr_pipeline.py` |

`uc13_full_pipeline.yml` uses **two tasks** (not one) so each phase has independent visibility, timeouts, and retries in the Databricks job UI. If ingestion fails, the diligence task is automatically blocked.

### VDR pipeline (UI-triggered) — `run_vdr_pipeline.py` + `run_vdr_job` notebook

The **VDR Diligence Pipeline** job (`617196299594076` in the Rallyday workspace) is how the Project Lighthouse UI runs diligence. Key facts:

- **Task = `notebook_task`** pointing at `jobs/notebooks/run_vdr_job` with **NO job/task parameters**. The UI triggers `run-now` passing **notebook params `table_name` + `record_id`** (note: `record_id`, not `id`), which arrive as widgets. Declaring fixed task parameters blocks the UI trigger — do not add them.
- The notebook reads the widgets and calls `run_vdr_pipeline(table_name, record_id)`, which reads a `rallyday_partners_llc.default.companies_vdr_history` row, runs `run_full_pipeline()` (Phase 1-5, catalog **hardcoded `uc13`**), copies `full_report.docx` (the orchestrator memo) + `executive_summary.docx` (the `agents/exec_summary` Rev3 one-pager bridge) to `/Volumes/rallyday_partners_llc/default/vdr/{company}/{ts}/`, and flips the record `processing → done`/`error`.
- **Code source = a Databricks Git folder** (`Rallyday`, under a user's `/Workspace/Users/…`) checked out to the working branch — NOT the job's `git_source` block (dead config). To ship code to the job: push, then `databricks repos update <id> --branch <b>`.
- **Vision is ON by default in this path** (Haiku), overridable via the `vision_endpoint` widget (`""` disables). SharePoint folder is resolved from the `sp_folder_path` secret + `company_name` (`{folder}/Example Data Room/{company_name}`); the record's `source_data_location` is display-only and NOT used.

### Phase 1-2 runner (`run_ingestion_pipeline.py`)

Sequential chain — no parallelism (each step depends strictly on the previous):
`download_upload` → `document_classifier` → `ingestion_parser` → `coverage_backfill` → `company_profiler`.

`parse_priority_tiers` defaults to `"1,2"` — only Tier 1 and Tier 2 documents are parsed by `ingestion_parser`. After the parse, `coverage_backfill` (Phase 2c) calls `ensure_coverage.main_coverage_backfill()`: it checks which workstreams have zero ingested documents and appends up to 2 best-available files per uncovered workstream from any remaining tier (APPEND only, never deletes). If `parse_priority_tiers="all"`, the `coverage_backfill` step is automatically SKIPPED. Failure isolation: if `download_upload` or `document_classifier` fail, all downstream steps are SKIPPED. If `ingestion_parser` fails, `coverage_backfill` is SKIPPED and `company_profiler` runs degraded (no embeddings; profile fields will be null). The function is callable standalone or imported by `run_full_pipeline.py`.

### Phase 3-5 DAG (`agents/orchestration/pipeline.py`)

`agents/orchestration/pipeline.py` is the **single source of truth for the Phase 3→5 DAG** — there is no duplicate graph in any Workflow YAML. `run_diligence_pipeline.py` and `run_full_pipeline.py` both delegate to `run_pipeline()`.

- **DAG / dependencies**: BMA · FTA · CQA · KPI are independent; `legal_contracts` soft-depends on CQA (`contract_trigger_list`); `quality_of_earnings` hard-depends on FTA + soft on CQA; `forecast` hard-depends on FTA + soft on QofE/CQA. Phase 4 `cross_analysis` waits on all Phase 3; Phase 5 `orchestrator` hard-depends on `cross_analysis`.
- **Failure isolation:** each agent runs with retries (`max_retries`, default 2). On final failure, agents that **hard-depend** on it are `SKIPPED`; agents that only **soft-depend** run **degraded** (their `_load_*` fallbacks handle a missing upstream table). Independent agents always continue. The run manifest (`SUCCESS`/`FAILED`/`SKIPPED` + attempts + error + degraded_from) is persisted into `uc13.analysis.diligence_report.agent_run_manifest_json` and rendered in the memo appendix.
- **Parallelism + tracing:** independent agents run concurrently via a wave scheduler (`ThreadPoolExecutor`, `max_parallelism`). Each agent's `@mlflow.trace` spans emit per-thread, so per-agent MLflow tracing is preserved. `run_pipeline` drives Phases 3+4 through the DAG, then runs the Orchestrator explicitly so it receives the manifest.
- **Context discipline:** Cross-Analysis and the Orchestrator NEVER read `chunks`/`embeddings`/`reasoning_trace`. They consume `to_result_card()` (a size-bounded normalized summary derived from each agent's `*_json` columns) plus targeted reads of specific JSON fields. Cross-Analysis reconciliation checks (§10.1) are deterministic Python; the LLM is used only for CIM-claims extraction (§10.2) and top-10 ranking (§10.3). The Orchestrator assembles the memo from each agent's `generate_*_assessment()` (each reads only its own row → bounded context per call); the only cross-cutting LLM call is the executive summary over a compact digest.
- **Final deliverable:** Markdown + Word memo only. Deck/one-pager/PDF are out of scope; `diligence_report.deliverables_json` is the extensible hook to add them later without a migration.

---

## Key design rules

### Ingestion — three modes, never mix them

- **`ingestion_parser.py main()`**: DELETE all rows for the company → parse approved files (filtered by `parse_priority_tiers`) → APPEND fresh. Idempotent full rebuild. Use when extraction logic changes.
- **`ensure_coverage.py main_coverage_backfill()`**: Automatic post-parse safety net, called by `run_ingestion_pipeline` (Phase 2c). Finds workstreams with 0 ingested docs, picks the 1-2 best available files per uncovered workstream from any tier, and appends them. APPEND only. Only runs when `parse_priority_tiers != "all"`.
- **`ensure_coverage.py ingest_missing()`**: APPEND only, never deletes. Use manually when a workstream is missing files after the main parse. Always check with `get_coverage_report()` first (Cell 8c), then fill with `ingest_missing()` (Cell 8d). Accepts optional `file_names_whitelist: set[str]` to restrict to specific files.

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

The base class default is `max_tokens=12_000`. Agents with especially large extraction schemas should pass an explicit override. The assessment narrative LLM call is a separate invocation and has its own `max_tokens` (6,000). Never rely on the default for production agents — set it explicitly in each `_call_llm()` call so truncation budget is visible at the call site.

**Serving read timeout ≈ 120s — single calls must finish under it.** The Databricks serving read timeout is ~120s per request (not reliably raised by env vars). A ~12K-token Sonnet generation completes under it; **~16K does not** and dies with `TimeoutError: Timed out after 0:10:00` (retries until the 10-min budget). Consequences:
- **BMA extraction is split into TWO bounded passes** (`business_model_agent.py`): commercial fields and organizational fields, each `max_tokens=8_000`, combined by taking each group's fields from its own pass. Do not collapse it back to a single 16K call. This is the FTA sub-agent pattern applied to BMA.
- If any other agent's single extraction grows past ~12K output, split it the same way rather than raising `max_tokens`.

### Assessment generators — `flags` is a JSON STRING column

Several analysis tables persist `flags` as a **`STRING`** column (JSON), while `data_room_gaps` is `ARRAY<STRING>`. A `generate_*_assessment()` that loads a Delta row therefore gets `flags` as a **str**, not a list. Any code that iterates it (e.g. `sorted(flags, key=lambda f: f.get("severity"))`) must **deserialize defensively first** (`json.loads(x) if isinstance(x, str) else (x or [])`, then keep only dict elements) — otherwise it iterates the string's characters and raises `'str' object has no attribute 'get'`, which makes the orchestrator fall back to a generic memo section. Already fixed in `business_model_agent.py` and `financial_trends_agent.py`; audit the others (CQA/KPI/QoE/Legal/Forecast) if a section falls back.

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
- **SparkSession**: use `SparkSession.getActiveSession()` inside scripts for single-threaded code. In `ThreadPoolExecutor` worker threads (e.g. `pipeline.py` agent parallelism), the thread-local active session is `None` — `PipelineOrchestrator._run_agent()` calls `SparkSession.builder.getOrCreate()` at thread start to register the shared JVM session for that thread. Do not add this call to individual agent `main()` functions; it belongs only in the orchestration layer.
- **`ai_parse_document`**: Databricks SQL function (version 2.0). Returns elements with types: `title`, `section_header`, `text`, `table` (HTML content), `figure` (empty content for images/charts), `page_footer`, `page_number`. Table content is raw HTML — always use `_html_table_to_markdown()`, never `_strip_html()` on table elements.
- **Vector Search**: use `WorkspaceClient().vector_search_indexes.query_index()`. The `retrieval.py` fallback uses keyword LIKE search when VS fails.
- **`%pip install`** in notebooks restarts Python — Cell 1 (Config) must always be re-run after Cell 0.

---

## Industry overlays

The company profiler detects one of: `healthcare`, `tech_services`, `b2b_saas`, `industrial`, `consumer`. Overlay-specific fields in the business model output are nested under `customer_profile_json → overlay_specific → {healthcare|tech_services|b2b_saas}`. Completeness checks in the agent are gated on the confirmed overlay — do not add overlay-specific logic to the base extraction path.

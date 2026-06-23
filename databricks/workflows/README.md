# UC13 Ingestion Pipeline — Deployment & Operations Guide

## Overview

The UC13 Ingestion Pipeline is a Databricks Workflow that ingests private-equity
due-diligence documents from a SharePoint data room, classifies them with an LLM,
parses them into semantic chunks, generates embeddings, and builds a structured
company profile.

```
00_setup_vector_search   (run once per environment)
        ↓
01_download_upload        Phase 1 — SharePoint → UC Volume
        ↓
02_document_classifier    Phase 2a — LLM workstream tagging + priority detection
        ↓
03_ingestion_parser       Phase 2b — chunking + embeddings  ┐ (run sequentially;
        ↓                                                     │  parser must finish
04_company_profiler       Phase 2b — semantic search + LLM  ┘  before profiler)
```

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Databricks workspace with Unity Catalog | Workspace admin must create the `uc13` catalog |
| MLflow serving endpoints | `databricks-bge-large-en` and `databricks-meta-llama-3-3-70b-instruct` must be active |
| Vector Search enabled | Feature toggle must be on for the workspace |
| SharePoint App Registration | Azure AD app with `Sites.Read.All` and `Files.Read.All` application permissions granted by the tenant admin |
| Repo cloned to Databricks Repos | Clone `uc-13-ale` repo into the workspace so script paths resolve correctly |

---

## 2. Required Secrets Scope

Create a Databricks secrets scope named **`uc13`** and add the following keys.

```bash
# Create the scope (run once)
databricks secrets create-scope uc13

# SharePoint / Microsoft Graph credentials
databricks secrets put --scope uc13 --key sp_tenant_id
databricks secrets put --scope uc13 --key sp_client_id
databricks secrets put --scope uc13 --key sp_client_secret
databricks secrets put --scope uc13 --key sp_site_url        # full HTTPS URL of the SP site
databricks secrets put --scope uc13 --key sp_folder_path     # drive-relative path, e.g. /Nimble Gravity UC13
```

Key names must match **exactly** (lowercase with underscores) because the scripts
call `dbutils.secrets.get("uc13", key)`.

Locally, the same keys must appear in `databricks/.env` using the **same** names:

```
sp_tenant_id=...
sp_client_id=...
sp_client_secret=...
sp_site_url=https://yourorg.sharepoint.com/teams/YourSite
sp_folder_path=/Nimble Gravity UC13
```

---

## 3. Deploying the Workflow

### Option A — Databricks Asset Bundle (recommended)

```bash
# Install the Databricks CLI
pip install databricks-cli

# Authenticate
databricks configure --token

# From the repo root
cd uc-13-ale
databricks bundle deploy --target dev     # or --target prod
databricks bundle run uc13_ingestion_pipeline --target dev \
  -p sp_company_name="Elder Care"
```

### Option B — Import via UI

1. Open the Databricks workspace → **Workflows** → **Create job**.
2. Click **Import** (top-right) and paste the contents of
   `databricks/workflows/uc13_ingestion_pipeline.yml`.
3. Set the **sp_company_name** job parameter to the target company name.

---

## 4. One-Time Setup (new environment)

Run `00_setup_vector_search` **once** before the first pipeline run:

```bash
databricks bundle run uc13_ingestion_pipeline \
  --task setup_vector_search \
  -p sp_company_name="any"
```

This creates:
- Unity Catalog schemas `uc13.ingestion` and `uc13.classification`
- The `uc13.ingestion.embeddings` Delta table (CDF enabled)
- The `uc13-vector-search` Vector Search endpoint
- The `uc13.ingestion.embeddings_index` Delta Sync index

For subsequent company runs, skip this task by running the pipeline from
`download_upload` onwards (or leave it in — it is idempotent and fast).

---

## 5. Running for a New Company

The only thing that changes between companies is the **`sp_company_name`** parameter.
No code changes are needed.

```bash
# UI: Workflows → UC13 Ingestion Pipeline → Run Now
# Set sp_company_name = "Project Silo"

# CLI:
databricks bundle run uc13_ingestion_pipeline \
  -p sp_company_name="Project Silo"
```

Each company's files land in a separate Volume subfolder:

```
/Volumes/uc13/ingestion/raw_files/
├── Elder Care/
│   └── 00. CIM/
│       └── Elder Care CIM v2.pdf
└── Project Silo/
    └── ...
```

Classification and profiling rows are written with the company name embedded
so different companies coexist in the same tables without collision.

---

## 6. Dependency Order and Why It Matters

### Phase 1 must complete before Phase 2

`01_download_upload` writes files to the Volume **and** writes `uc13.ingestion.upload_log`
with Priority Tier signals. The classifier (`02_document_classifier`) reads that table
to seed its LLM prompt, so running them concurrently would give the classifier no signal.

### Classifier must complete before Parser and Profiler

`02_document_classifier` writes `uc13.classification.doc_relevance` — the gate table
that controls which files get parsed (`should_parse=true`) and which workstream tags
are indexed alongside each embedding.

Without `doc_relevance`, the parser has no file list and the profiler has no workstream
filter to restrict retrieval to high-signal document types.

### Parser must complete before Profiler

`03_ingestion_parser` generates the embeddings that `04_company_profiler` queries via
Vector Search. Running the profiler before embeddings exist returns empty results for
every profiling dimension.

**Priority Tier documents are processed first** within the parser (ORDER BY priority_tier DESC)
so that CIMs, QofE reports, and financial models are available in the index before
background documents are chunked. This matters when the profiler runs immediately after
the parser in a time-constrained window.

---

## 7. Monitoring and Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `01_download_upload` fails with 401 | SharePoint client secret expired or wrong | Rotate secret in Azure AD; update `uc13/sp_client_secret` |
| `02_document_classifier` returns all BACKGROUND | LLM endpoint rate-limited or unreachable | Check endpoint status in Serving; retry |
| `04_company_profiler` returns all nulls | No embeddings in the index (parser didn't finish, or index not yet synced) | Wait for index sync; check `embeddings_index` status in Vector Search UI |
| Profile `company_name` is blank | `sp_company_name` parameter not set | Set the parameter before running |
| `data_room_gaps` lists "No CIM found" | CIM not present in data room or not uploaded | Add the CIM to SharePoint and re-run Phase 1 |

---

## 8. Local Development

Scripts run locally as long as `databricks/.env` is populated (see Section 2).
Spark-dependent steps (`spark.sql`, Delta writes) will raise `NameError: 'spark'` —
this is expected; those steps only execute on a Databricks cluster.

```bash
cd databricks
uv sync                           # install deps from pyproject.toml
uv run python jobs/scripts/01_download_upload.py    # requires .env
```

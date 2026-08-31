# Corpus Baseline Reference — Elder Care LEGAL

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | Elder Care |
| **run date** | 2026-06-25 |
| **use** | Reference context for interpreting `legal_register` S2 verifier coverage |

Aggregate LEGAL embedding/chunk counts and filename decomposition for the Elder Care legal corpus. Chunk count is 1:1 with embeddings on this catalog.

---

## Workstream gate (LEGAL)

Source: `classification.doc_relevance` + `ingestion.chunks` (company-scoped).

| workstream | file_count | should_parse_rows |
|------------|------------|-------------------|
| FINANCIAL | 524 | 249 |
| **LEGAL** | **137** | **135** |
| CUSTOMER | 8 | 8 |

LEGAL file count is ~26% of FINANCIAL (137 vs 524). Gate: 135/137 files parse-approved — sufficient coverage to proceed.

---

## Embedding volume by workstream

Source: `ingestion.embeddings` (company-scoped; `workstream` exploded).

| workstream | embedding_rows | distinct_files |
|------------|----------------|----------------|
| FINANCIAL | 23,798 | 94 |
| KPI_OPS | 8,693 | 7 |
| QUALITY_EARNINGS | 5,472 | 15 |
| **LEGAL** | **1,347** | **78** |
| FORECAST | 1,341 | 3 |
| BUSINESS_MODEL | 1,198 | 27 |
| CUSTOMER | 89 | 8 |

LEGAL embedding rows ≈ **5.7%** of FINANCIAL (1,347 / 23,798).

---

## LEGAL filename decomposition

Source: `ingestion.embeddings` JOIN `classification.doc_relevance` WHERE `array_contains(workstream, 'LEGAL')`.

### Keyword buckets

| bucket | files | chunks |
|--------|-------|--------|
| other | 62 | 949 |
| lease | 9 | 348 |
| insurance | 4 | 17 |
| ip_privacy | 1 | 14 |
| MSA | 1 | 12 |
| litigation | 1 | 7 |

**employment keyword bucket:** empty at filename level.

### Top filenames by chunk count (top 10)

| file_name | chunk_count | max_tier |
|-----------|-------------|----------|
| Elder Care Homecare - Unicity Handbook 09.2024.docx | 99 | 2 |
| Manhattan_Lease_0424.pdf | 98 | 2 |
| New and Annual Employee Orientation.pdf | 93 | 2 |
| Elder Care bond renewal (2).pdf | 77 | 2 |
| Long Island_Lease_0423.pdf | 64 | 2 |
| Guided Living - Asset Purchase Agreement - 02.07.24 - Execution Version with Exhibits, Lease, and BOS - signed (1).pdf | 49 | 1 |
| Westchester & LI DOH Survey Approval 5.10.2018.pdf | 47 | 2 |
| Westchester_Lease_0121.pdf | 47 | 2 |
| Staffing Contract_The Club_0923.pdf | 36 | 2 |
| Unicity_Asset Purchase Agreement_0824.pdf | 36 | 1 |

### Decomposition notes

- Corpus is **lease-heavy** (348 chunks / 9 files) and **handbook/orientation-heavy** (top file: Unicity Handbook, 99 chunks).
- Service agreements appear as `* SA.pdf` / `*Agreement*` filenames but often land in **other** bucket — not captured by generic `MSA` token alone.
- Employment-oriented filenames exist in LEGAL tag (e.g. Employee Orientation, 401(k) agreement) but **employment keyword bucket is empty** at filename level.

Source: .dev/archive/legal_agent/corpus_baseline_elder_care.md

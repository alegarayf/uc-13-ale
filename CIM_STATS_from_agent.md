Here’s what’s in **`uc13_ale`** for CIM (Confidential Information Memorandum) files — queried from `ingestion.chunks`, `ingestion.upload_log`, and `ingestion.embeddings`.

## Coverage by company

| Company | CIM document | In DB? |
|---------|--------------|--------|
| **Clearsulting** | `Project Infinity  - Confidential Information Memorandum.pdf` | Yes (filename has no “CIM”) |
| **Elder Care** | `2024 Elder Care - CIM_vF.pdf` | Yes |
| **GKF** | `Project Ajax CIM vF - Rallyday Partners.pdf` | Yes |
| **SPG** | — | **No CIM** in upload log or chunks |

Clearsulting’s CIM is tagged `priority_reason = 'CIM'` in upload_log but the filename says “Confidential Information Memorandum”, not “CIM”.

GKF also has Teaser and IOI process letter in a “CIM” folder — those are **not** the actual CIM memo.

---

## Per-file stats

| Metric | Clearsulting | Elder Care | GKF |
|--------|-------------|------------|-----|
| **File size** | 6.48 MB (6,792,719 bytes) | 4.28 MB (4,484,169 bytes) | 5.54 MB (5,814,306 bytes) |
| **PDF mod date** | 2025-10-14 | 2025-05-19 | 2025-12-01 |
| **Page range** | 1–82 (82 pages) | 1–58 (58 pages) | 1–79 (79 pages) |
| **Chunks** | 941 | 502 | 473 |
| **Total chars** (`char_count`) | 309,605 | 196,867 | 210,285 |
| **Avg chars/chunk** | 329 | 392 | 444 |
| **Median chars/chunk** | 195 | 198 | 237 |
| **Min chars/chunk** | 111 | 112 | 136 |
| **Max chars/chunk** | 6,038 | 3,776 | 5,297 |
| **Est. words** (space-split) | 39,272 | 30,801 | 30,986 |
| **Est. tokens** (chars ÷ 4) | 77,401 | 49,216 | 52,571 |
| **Est. tokens** (chars ÷ 3.5) | 88,458 | 56,247 | 60,081 |

There is no dedicated `token_count` column — tokens are estimated from `char_count`.

---

## Chunk type breakdown

| Type | Clearsulting | Elder Care | GKF |
|------|-------------|------------|-----|
| **text** | 253 | 100 | 127 |
| **table** | 21 | 49 | 43 |
| **vision** | 667 | 353 | 303 |

Clearsulting is heavily vision-heavy (71% of chunks). Elder Care and GKF are ~70% vision as well.

---

## Char length distribution (chunks per bucket)

| Bucket | Clearsulting | Elder Care | GKF |
|--------|-------------|------------|-----|
| &lt; 200 chars | 494 | 256 | 137 |
| 200–500 | 319 | 152 | 218 |
| 501–1,000 | 81 | 56 | 71 |
| 1,001–2,000 | 33 | 26 | 39 |
| &gt; 2,000 | 14 | 12 | 8 |

Most chunks are short (&lt; 500 chars), which fits PDF page/slide chunking.

---

## Per-company totals

| Company | CIM docs | Total chunks | Total chars | Avg chars/chunk | Est. words | Est. tokens (÷4) |
|---------|----------|--------------|-------------|-----------------|------------|------------------|
| Clearsulting | 1 | 941 | 309,605 | 329 | 39,272 | 77,401 |
| Elder Care | 1 | 502 | 196,867 | 392 | 30,801 | 49,216 |
| GKF | 1 | 473 | 210,285 | 444 | 30,986 | 52,571 |
| **SPG** | **0** | — | — | — | — | — |

---

## Embeddings

All CIM chunks are embedded: 941 / 502 / 473 respectively (100% coverage).

---

## Notes

1. **SPG has no CIM** — no memorandum/CIM file in upload_log or chunks.
2. **Clearsulting CIM is largest** in extracted text (~310K chars, ~77K est. tokens) despite being the longest PDF (82 pages).
3. **Elder Care CIM is smallest** in extracted text (~197K chars) — fewer pages and fewer vision chunks.
4. **`uc13` prod catalog** has slightly higher chunk counts (Elder Care 519 vs 502, GKF 513 vs 473) — `uc13_ale` is the dev/eval catalog you’re on.
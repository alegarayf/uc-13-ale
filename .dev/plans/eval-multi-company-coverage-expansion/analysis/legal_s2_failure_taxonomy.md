# Legal S2 failure taxonomy — Elder Care 20/23 failures

**Plan:** eval-multi-company-coverage-expansion · **T7 report (2)**  
**Generated:** 2026-08-18 (M3 dump + live register cross-check; read-only)

## Question

For Elder Care `legal_register` S2, what drives the **20/23 claim failures** — retrieval miss, extraction/quote fidelity, or register-schema/corpus gap?

## Evidence refs

| Ref | Role |
|-----|------|
| `.dev/audits/eval-consolidation/M3/s2_scores_elder_care_dump.json` | Authoritative claim-level verdicts |
| `run_id:20260813T183720Z-r3f` | Latest legal_register S2 run (23 claims) |
| `uc13_ale.analysis.legal` | Register JSON columns for quote/source cross-check |
| `eval/LCA/presentation_summary_elder_care.md` | G1 checklist framing (7/11 assessed) |
| `eval/LCA/poc_delta_elder_care.md` | T4C/CoC/platform/IP gap taxonomy |
| `eval/program/product_backlog.yaml` | PB-legal_register-* backlog items |

## Run accounting (M3 dump)

| Verdict | Count |
|---------|-------|
| `supported` | 3 |
| `unsupported` | 13 |
| `contradicted` | 7 |
| **Failed (non-supported)** | **20** |

All 23 `claim_id`s trace to the dump (`legal.{register}.{index}` pattern). No fabricated IDs.

## Taxonomy buckets

Classification uses deterministic verifier semantics (`eval/content/legal_register_verifier.py`):

| Bucket | Count | Mechanism | Verifier signal |
|--------|-------|-----------|-----------------|
| **A — Retrieval miss** | **9** | `source_doc`/`source_location` did not resolve to any corpus chunk | `cited_chunk_id` is **null**, verdict `unsupported` |
| **B — Extraction / quote fidelity** | **11** | Register row exists with `raw_quote`, chunk resolved, but quote is not verbatim in corpus | 4× `unsupported` **with** chunk + 7× `contradicted` (prefix anchor only) |
| **C — Register schema / corpus gap** | **0 claim rows** | Checklist items with empty registers or `not_found` nested fields | Surfaces at **G1** (`unable_to_assess`), not in the 23 S2 claims |

Bucket C is still load-bearing for trust framing (`20/23` alongside G1 `7/11`) — see §Checklist crosswalk below.

## Per-claim breakdown (20 failures)

### A — Retrieval miss (9)

| claim_id | register row source_doc (truncated) | quote prefix |
|----------|-------------------------------------|--------------|
| `legal.contract_register.0001` | Manhattan_Lease_0121.pdf | Licensor has not made and is not making any warranties… |
| `legal.contract_register.0002` | Long Island_Lease_0423.pdf \| Westchester | without the prior consent of Landlord… |
| `legal.employment_register.0001` | Kate Marks Restricted Stock.pdf | Nothing in this Agreement or in the Plan… |
| `legal.employment_register.0003` | Manhattan_Lease_0424.pdf | Contractor shall defend, indemnify… |
| `legal.insurance_register.0000` | Elder Care NY COI.pdf | COMMERCIAL GENERAL LIABILITY… |
| `legal.insurance_register.0001` | Elder Care NY COI.pdf | AUTOMOBILE LIABILITY… |
| `legal.insurance_register.0002` | Elder Care NY COI.pdf | THIS CERTIFICATE IS ISSUED… |
| `legal.litigation_register.0000` | April 30 2025 Fully Executed Retainer… | we propose to represent Eldercare… |
| `legal.privacy_security_register.0000` | Jotform BAA agreement.pdf | This HIPAA BAA is effective… |

**Fix lane:** chunk-id resolver / locator parsing (page vs section; multi-doc lease rows; COI table layout).

### B — Extraction / quote fidelity (11)

**Unsupported with chunk (4)** — full quote absent from resolved chunk(s):

| claim_id | cited_chunk_id | source_doc |
|----------|----------------|------------|
| `legal.contract_register.0000` | `e504f67e-…` | Manhattan_Lease_0424.pdf |
| `legal.contract_register.0003` | `0418b165-…` | Xerox Lease.pdf |
| `legal.privacy_security_register.0001` | `7fb62b5a-…` | Jotform BAA agreement.pdf |
| `legal.vendor_register.0000` | `0c6b4eba-…` | Manhattan_Lease_0424.pdf |

**Contradicted (7)** — six-word prefix anchor matches but full `raw_quote` does not (paraphrase / truncation):

| claim_id | cited_chunk_id | source_doc |
|----------|----------------|------------|
| `legal.employment_register.0000` | `54572acb-…` | Non-Compete-Non Solicitation Agreement… |
| `legal.employment_register.0002` | `636add34-…` | 7 Employee Non-Disclosure.docx |
| `legal.privacy_security_register.0002` | `05becf73-…` | dropbox_hipaa_agreement.pdf |
| `legal.privacy_security_register.0004` | `a857b37c-…` | dropbox_hipaa_agreement.pdf |
| `legal.privacy_security_register.0005` | `9be8778d-…` | Elder Care Homecare, Inc_CC-BAA… |
| `legal.privacy_security_register.0006` | `d580e779-…` | Elder Care Homecare, Inc_CC-BAA… |
| `legal.vendor_register.0001` | `0418b165-…` | Xerox Lease.pdf |

**Fix lane:** product — tighten extraction prompts to emit verbatim quotes; consider multi-chunk enumeration (verifier already scans sibling chunks).

### Supported (3) — reference

| claim_id | register |
|----------|----------|
| `legal.contract_register.0004` | contract_register |
| `legal.privacy_security_register.0003` | privacy_security_register |
| `legal.privacy_security_register.0007` | privacy_security_register |

## Checklist crosswalk (G1 vs S2)

The four G1 `unable_to_assess` items from `poc_delta_elder_care.md` explain **checklist** gaps but do **not** appear as separate rows in the 23-claim S2 set (no traceable register quotes):

| Checklist item | poc_delta class | product_backlog ref |
|----------------|-----------------|---------------------|
| Termination for convenience (`t4c`) | Extraction depth | `PB-legal_register-extraction-depth-contracts` |
| Change-of-control (`coc`) | Extraction depth | same |
| Platform / channel (`platform`) | Corpus gap | `PB-legal_register-corpus-gap-platform` |
| IP ownership (`ip`) | Corpus / retrieval miss | `PB-legal_register-retrieval-ip` |

S2 failures on **populated** registers (contracts, employment, insurance, privacy, vendor, litigation) are dominated by **A+B** (retrieval + quote fidelity), not missing register columns.

## Summary

| Layer | Share of 20 failures | Primary product action |
|-------|---------------------|------------------------|
| Retrieval miss | 9 (45%) | Locator/chunk resolution hardening |
| Quote fidelity | 11 (55%) | Verbatim quote extraction + chunk boundary handling |
| Register schema / corpus | 0 S2 claims; 4 G1 gaps | Ingest expansion (platform/IP) + nested-field extraction (T4C/CoC) |

Trust statement `20/23 legal_register claim failures` is **claim-level traceability debt** on existing register rows, orthogonal to the G1 `7/11` structural pass count.

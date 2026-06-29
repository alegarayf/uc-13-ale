# POC Delta — Elder Care Legal Agent (G4)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` (`sp_company_name`) |
| **git SHA** | `12853d40c0dba9f710d107228a6c002d3655bb1e` |
| **E2E timestamp** | `2026-06-29T12:39:35Z` (Cell 16 `created_at`) |
| **spec ref** | `legal_agent.md` §5.6 (`STAKEHOLDER_COVERAGE_REQUIREMENTS`), Eval Approach G4 |
| **milestone** | M3 — Schema guard, tests, E2E & stakeholder closure (T4) |

## E2E run record (D5-C)

| Step | Cells | Action |
|------|-------|--------|
| Config | **1** | Widgets/env: `catalog=uc13_ale`, `sp_company_name=Elder Care`, Sonnet `extraction_endpoint` |
| LEGAL coverage gate | **8c** | **1,347** LEGAL embedding rows — gate **PASS** (pre-existing; skipped 7→8) |
| Company profile | **9→10** | **Skipped** — `classification.company_profile` row pre-existing |
| Legal agent | **16** | `legal_contracts_agent.main()` — Delta append + dual Volume YAML |
| Table verify | **18** | `analysis.legal` row `section_confidence=high`; compat view `legal_contracts` OK |
| Volume compare | operator | `_compare_baselines.py --catalog uc13_ale` (D4-A dual compare) |

**Skipped:** Cells 3–6, 11–15, 17; Cell 8d (LEGAL coverage sufficient).

**Pre-sync note:** First Cell 16 attempt used stale workspace `legal_contracts_agent.py` (pre-M2 shape). Agent re-uploaded from repo HEAD before second run; all metrics below are from the **second** run.

## Dual compare summary (D4-A)

### Arm 1 — legacy `legal_contracts_report.yaml` vs A1 baseline

| Metric | A1 baseline (M0) | M3 latest (2026-06-29) |
|--------|------------------|------------------------|
| `contract_register` | 14 | 5 |
| `litigation_register` | 2 | 1 |
| `flags` | 6 | 8 |
| `data_room_gaps` | 1 | 4 |
| `citations` | 10 | 23 |
| `executive_summary` len | 739 | 246 |

**Result:** `DIFFER` (154 leaf differences). Expected — M1 multi-pass extraction + M2 merge/flags/gaps replaced monolithic M0 extraction; register counts are not parity targets.

### Arm 2 — normative `legal_report.yaml` vs Stakeholder Outline

| Check | Result |
|-------|--------|
| Outline keys present | **12/12** (`OUTLINE_OK`) |
| `confidence` | `high` |
| `unable_to_assess` bullets (total) | 4 |
| `Recommended Legal Diligence` | 1 (healthcare overlay) |
| Volume bytes | legacy 21,167 · normative 22,300 |

## Assessed vs unpopulated (11-item checklist)

**Assessed (7/11):** `restrictive`, `vendor`, `employment`, `founder`, `litigation`, `privacy`, `insurance`

**Unpopulated / `unable_to_assess` (4/11):** traced below — not spec omissions.

---

## §5 gap traceability (G4)

Each unpopulated item maps to **corpus gap**, **retrieval miss**, or **extraction depth** with A0 corpus baseline citation (`.dev/legal_agent/corpus_baseline_elder_care.md`).

### 1. Customer contracts — termination for convenience (`t4c`)

| Classification | **Extraction depth** |
|----------------|----------------------|
| Evidence | Contracts pass retrieved **14 chunks** from 4 files (APA, Manhattan/Long Island leases). `contract_register`=5 rows with `source_doc` citations, but `_pred_t4c` false — `termination_for_convenience.present` remains `not_found` on all contract rows. |
| A0 cite | §3: lease-heavy corpus (348 chunks / 9 lease files); §4 dry-run contracts pass returned only 7/14 `top_k` slots — dense lease/APA mix limits T4C clause surfacing in 5 merged contract rows. |
| Agent gap string | `t4c: chunks retrieved but no extractable terms` |

### 2. Change-of-control clauses (`coc`)

| Classification | **Extraction depth** |
|----------------|----------------------|
| Evidence | Same contracts pass: CoC nested fields (`clause_present`, `consent_required`, thresholds) predominantly `not_found` despite lease-heavy retrieval. M0 A1 baseline extracted explicit CoC on Manhattan/Westchester leases via monolithic prompt; multi-pass per-domain schemas did not re-surface those fields in M3 run. |
| A0 cite | §3 top filenames include `Manhattan_Lease_0424.pdf` (98 chunks), `Westchester_Lease_0121.pdf` (47) — corpus **contains** CoC-bearing leases; failure is extraction depth, not zero LEGAL coverage. |
| Agent gap string | `coc: chunks retrieved but no extractable terms` |

### 3. Platform / reseller / channel dependencies (`platform`)

| Classification | **Corpus gap** (with retrieval miss within pass) |
|----------------|--------------------------------------------------|
| Evidence | `platform_dependency_register`=0; gap classifier used contracts_vendors_platform pass chunk count ≥1 → "chunks retrieved but no extractable terms". No platform/reseller/channel agreement filenames in A0 LEGAL decomposition. |
| A0 cite | §3 keyword buckets: no `platform`/`channel`/`reseller` bucket; top-30 filenames are leases, APA, staffing, SA, handbook — **no dedicated platform dependency agreements** tagged LEGAL. |
| Agent gap string | `platform: chunks retrieved but no extractable terms` |

### 4. IP ownership, assignment, OSS (`ip`)

| Classification | **Retrieval miss** |
|----------------|-------------------|
| Evidence | `ip_register`=0 while `privacy_security_register`=8 from same `ip_privacy` pass (BAAs, HIPAA agreements). `_pred_ip` requires `ip_register` rows with `source_doc`. |
| A0 cite | §3: `ip_privacy` bucket **1 file / 14 chunks** (`dropbox_hipaa_agreement.pdf`); §4 dry-run ip_privacy pass returned 2 chunks — corpus lacks IP assignment, OSS policy, or trademark filings in LEGAL-tagged set. Privacy obligations retrieved; IP ownership docs not in retrieval set. |
| Agent gap string | `ip: chunks retrieved but no extractable terms` |

---

## Items assessed (no POC delta required)

| item_id | Register evidence | Notes |
|---------|-------------------|-------|
| `restrictive` | 5 contract rows + restrictive covenant flags | Lease anti-assignment / APA covenants surfaced |
| `vendor` | 1 `vendor_register` row | Staffing/vendor agreement extracted |
| `employment` | 2 `employment_register` rows | Handbook + restricted stock (A0 §6: employment filename bucket empty at A0; M1 B2 tuning improved yield) |
| `founder` | `agreement_class=founder_key` in employment register | Kate Marks restricted stock |
| `litigation` | 1 open collection retainer matter | A0 §4 dry-run litigation=0; M1 filter retry (`retrieval_fallback`) improved yield |
| `privacy` | 8 `privacy_security_register` rows | BAA / HIPAA corpus (A0 §4: 2 chunks dry-run → 8 rows post-tuning) |
| `insurance` | 4 `insurance_register` rows | COI + bond renewal (A0 §4: 4 chunks dry-run, consistent) |

## Recommended diligence (not a §5 checklist gap)

Healthcare overlay appended `Healthcare Referral Agreements` (High) per `_is_healthcare_overlay` — informational diligence item, not one of the 11 `STAKEHOLDER_COVERAGE_REQUIREMENTS` rows.

## Compare tooling

```bash
python .dev/legal_agent/_compare_baselines.py --catalog uc13_ale --company "Elder Care"
python .dev/legal_agent/_compare_baselines.py --catalog uc13_ale --json
```

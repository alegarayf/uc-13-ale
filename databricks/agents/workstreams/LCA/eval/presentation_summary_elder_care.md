# Legal Agent — Elder Care Stakeholder Summary (D2)

| Field | Value |
|-------|-------|
| **company** | Elder Care (`sp_company_name`) |
| **catalog** | `uc13_ale` |
| **run date** | 2026-06-29 (`created_at` 12:39:35Z) |
| **git SHA** | `12853d40c0dba9f710d107228a6c002d3655bb1e` |
| **milestone** | M3 — Schema guard, tests, E2E & stakeholder closure (T6) |
| **normative report** | `/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml` |

---

## Coverage snapshot

| Metric | Value | Source |
|--------|-------|--------|
| **Assessed items** | **7 of 11** | `assess_coverage_gaps` / normative `executive_summary` (T4 E2E) |
| **Section confidence** | **high** | `confidence` field + `_compute_section_confidence` (7 assessed → high band) |
| **Option-C flags** | **8** | Normative `Flags` section (5 restrictive covenant, 2 unusual indemnity, 1 open matter) |
| **Unable to assess** | **4** | §5 checklist gaps surfaced in report (not spec omissions) |
| **Recommended diligence** | **1** | Healthcare overlay (referral agreements) |

**Assessed count derivation:** T5 golden checklist was not yet on disk at T6 execution; numerator **7** is taken from the M3 E2E agent output (`executive_summary`: “7 of 11 checklist items had extractable supporting terms”). Denominator **11** is `STAKEHOLDER_COVERAGE_REQUIREMENTS`. When T5 lands, pass + partial rows should reconcile to this numerator.

---

## What the agent extracted (7 assessed)

| Area | Evidence | Stakeholder note |
|------|----------|------------------|
| Restrictive covenants | 5 contract rows; 5 Yellow flags | APA + Manhattan/Long Island leases — anti-assignment and operational covenants |
| Vendor terms | 1 vendor register row | Staffing / contractor terms from lease exhibit |
| Employment | 2 employment register rows | Handbook (at-will) + restricted stock |
| Founder / key employee | `founder_key` on Kate Marks restricted stock | Key-person equity terms surfaced |
| Litigation | 1 open collection retainer | Red flag — outside counsel for receivables collection |
| Privacy / security | 8 privacy register rows | BAAs (Jotform, Dropbox, Clearcare) — HIPAA obligations |
| Insurance | 4 insurance register rows | GL, auto, COI, crime bond from NY COI + bond renewal |

---

## Top gaps (4 of 11)

Each item is correctly classified as **unable to assess** with retrieval context; detail and A0 corpus cites are in [POC delta](poc_delta_elder_care.md).

| Checklist item | Classification | One-line why |
|----------------|----------------|--------------|
| Termination for convenience (`t4c`) | Extraction depth | Contracts pass retrieved 14 chunks; no `termination_for_convenience.present=true` in merged register |
| Change-of-control (`coc`) | Extraction depth | Lease-heavy corpus (A0 §3); CoC nested fields `not_found` despite M0 monolithic baseline surfacing lease CoC |
| Platform / channel (`platform`) | Corpus gap | No platform/reseller/channel agreements in LEGAL-tagged filenames (A0 §3 keyword buckets) |
| IP ownership / OSS (`ip`) | Retrieval miss | `ip_register` empty; same pass yielded 8 privacy rows from HIPAA BAAs only (A0 §3 `ip_privacy` = 1 file) |

**Healthcare diligence (informational):** Recommended **Healthcare Referral Agreements** (High) — overlay item, not one of the 11 checklist rows.

---

## Corpus context (A0)

From [corpus baseline](../corpus_baseline_elder_care.md):

- **1,347** LEGAL embedding rows across **78** files — sufficient to run multi-pass extraction (not a zero-coverage failure).
- Corpus is **lease-heavy** (348 chunks / 9 lease files) and **handbook-heavy** (Unicity Handbook top file).
- **Employment** and **litigation** dry-runs were 0 at A0; M1 B2 tuning improved yield (2 employment rows, 1 litigation matter in M3 run).
- **HR workstream overlap = 0** on Elder Care — employment pass must target LEGAL-tagged handbook/orientation filenames.
- LEGAL volume ≈ **5.7%** of FINANCIAL embeddings — directional thinness vs financial workstream, but gate **PASS** (1,347 rows).

---

## Flags at a glance

| Severity | Count | Themes |
|----------|-------|--------|
| Red | 1 | Open legal matter (collections retainer) |
| Yellow | 7 | Restrictive covenants (leases, APA); unusual indemnity (Manhattan lease) |

No change-of-control **consent** flags fired (consistent with CoC extraction gap above).

---

## E2E & eval artifacts

| Artifact | Path |
|----------|------|
| POC delta (G4) | `.dev/legal_agent/eval/poc_delta_elder_care.md` |
| Normative baseline (T4) | `.dev/legal_agent/baselines/_latest_Elder_Care_legal_report.yaml` |
| Golden checklist (T5 / G3) | `.dev/legal_agent/eval/golden_checklist_elder_care.md` *(pending)* |
| Compare tooling | `python .dev/legal_agent/_compare_baselines.py --catalog uc13_ale --company "Elder Care"` |

**Dual compare (D4-A):** Legacy A1 vs M3 **DIFFER** (expected — multi-pass rewrite). Normative outline **12/12 keys** (`OUTLINE_OK`).

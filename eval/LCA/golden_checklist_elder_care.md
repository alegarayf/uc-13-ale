# Golden Checklist — Elder Care Legal Agent (G3)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `12853d40c0dba9f710d107228a6c002d3655bb1e` |
| **E2E timestamp** | `2026-06-29T12:39:35Z` |
| **source YAML** | `/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml` |
| **spec ref** | `legal_agent.md` Eval Approach item 2; `STAKEHOLDER_COVERAGE_REQUIREMENTS` (§5.6) |
| **POC delta** | `.dev/legal_agent/eval/poc_delta_elder_care.md` |

**Verdict key:** `pass` — register populated with citation; `partial` — register partially populated; `gap-correct` — correctly surfaced as `unable_to_assess` when corpus thin or extraction depth insufficient; `n/a` — not applicable to this corpus.

## Checklist (11 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| t4c | Customer contracts — termination for convenience | gap-correct | `contract_register`=5 rows with citations; all `termination_for_convenience.present`=`not_found`. Listed in normative YAML `unable_to_assess` (Customer & Vendor Contracts). POC: extraction depth — chunks retrieved, no extractable T4C terms. |
| coc | Change-of-control clauses | gap-correct | `contract_register`=5 rows; all `change_of_control.clause_present`=`not_found`. Listed in normative YAML `unable_to_assess`. POC: extraction depth — lease corpus contains CoC-bearing docs but multi-pass did not surface fields. |
| restrictive | Exclusivity, MFN, non-compete, non-solicit | pass | 5 `contract_register` rows with `restrictive_covenants.present`=`true` and `source_doc` citations (APA, Manhattan/Long Island leases). |
| vendor | Vendor pricing / cancellation terms | pass | 1 `vendor_register` row — Manhattan lease contractor indemnification (`Manhattan_Lease_0424.pdf`). |
| platform | Platform / reseller / channel dependencies | gap-correct | `platform_dependency_register`=0; listed in normative YAML `unable_to_assess` (Platform & Channel Dependencies). POC: corpus gap — no platform/channel agreement filenames in LEGAL-tagged set. |
| employment | Employee, contractor, commission agreements | pass | 2 `employment_register` rows with `agreement_class`=`employee` and citations (handbook, restricted stock). |
| founder | Founder / key employee agreements | pass | 1 `employment_register` row — Kate Marks, `agreement_class`=`founder_key` (`Kate Marks Restricted Stock.pdf`). |
| litigation | Litigation exposure | pass | 1 `litigation_register` row — open collection retainer matter with `source_doc` citation. |
| privacy | Data privacy / security obligations | pass | 8 `privacy_security_register` rows — BAA/HIPAA obligations (Jotform, Dropbox, Clearcare). |
| ip | IP ownership, assignment, OSS | gap-correct | `ip_register`=0; listed in normative YAML `unable_to_assess` (IP, Privacy & Security). POC: retrieval miss — privacy pass yielded BAAs but no IP assignment/OSS docs in LEGAL corpus. |
| insurance | Insurance coverage gaps | pass | 4 `insurance_register` rows — COI, GL, auto, bond renewal with `source_doc` citations. |

**Summary:** 7 `pass`, 0 `partial`, 4 `gap-correct`, 0 `n/a` — matches agent assessed count 7/11 and `section_confidence`=`high`.

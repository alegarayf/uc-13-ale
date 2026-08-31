# Golden Checklist — Clearsulting Legal Agent

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6eea10fd-35b1-4e87-8820-df5997581cb7` (`uc13_ale.analysis.diligence_report` 2026-08-19 19:32:30; `agent_run_manifest_json` `legal_contracts` SUCCESS `finished_at` 2026-08-19T19:23:57, correlated to Legal analysis row `2026-08-19 19:23:48`) |
| **source table** | `uc13_ale.analysis.legal` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_legal()` (11-field; pass / partial / gap-correct; `t4c`, `coc`, `restrictive`, `platform`, `ip` can be `gap-correct`; `employment` can be `gap-correct` if the register is empty) |
| **authoring provenance** | queried `uc13_ale.analysis.legal` WHERE `company_name='Clearsulting'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:23:48; all eight registers JSON `[]`; `unable_to_assess_json` lists all 11 items; `section_confidence`=`low` |

**Verdict key:** `pass` — register meets `score_legal()` threshold with citation; `partial` — register below threshold (`vendor` empty; `founder` with no `founder_key`; `privacy` fewer than 5 rows; `insurance` fewer than 3 rows); `gap-correct` — absence correctly surfaced (`t4c` / `coc` / `restrictive` with no `true` clause; empty `platform` / `ip`; empty `employment` register; empty `litigation`). Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset). Downstream scoring uses agent-id `legal` (directory `eval/LCA/`).

## Checklist (11 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| t4c | Customer contracts — termination for convenience | gap-correct | `contract_register_json`=`[]` so no `termination_for_convenience.present`=`true`; `score_legal()` maps that to `gap-correct`. `unable_to_assess_json` lists "Customer contracts - termination for convenience". `data_room_gaps` / reasoning trace: contracts pass retrieved 0 chunks from 0 files (LEGAL workstream + MSA/SOW filename filter). Independent: 0 `doc_relevance` rows with workstream LEGAL; 0 ingested filenames containing contract/MSA/SOW/agreement; 0 of 2417 `ingestion.chunks` mention termination for convenience. POC: corpus gap - no customer MSAs in the ingested set. |
| coc | Change-of-control clauses | gap-correct | Empty `contract_register_json`; no `change_of_control.clause_present`=`true`. Independent: 0 change-of-control / change-in-control hits in Clearsulting chunks; CIM has no contracts section (TOC is Executive Summary through Appendix). POC: corpus gap - same missing MSA/SOW set as `t4c`. |
| restrictive | Exclusivity, MFN, non-compete, non-solicit | gap-correct | Empty register; no `restrictive_covenants.present`=`true`. Independent: 0 non-compete / non-solicit / most-favored / exclusivity hits in 2417 chunks. POC: corpus gap. |
| vendor | Vendor pricing / cancellation terms | partial | `vendor_register_json`=`[]`. `score_legal()` scores empty vendor as `partial` (not `gap-correct`). Independent: 0 vendor-contract / supplier-agreement filenames or cancellation-term hits. Rubric mapping, not a hidden vendor MSA: the corpus also lacks vendor contracts. |
| platform | Platform / reseller / channel dependencies | gap-correct | `platform_dependency_register_json`=`[]` so `score_legal()` is `gap-correct`. Agent retrieved 0 LEGAL chunks. Independent: `Project Infinity - Technology Partnerships Deep Dive.pdf` is tagged BUSINESS_MODEL (not LEGAL) and describes partner marketing (BlackLine, Kyriba, Coupa "Source to Contract" product module) rather than reseller/platform *agreements*. No Referral / Channel / Platform Agreement filenames. POC: corpus gap for legal instruments; the partnerships deck is not a substitute contract. |
| employment | Employee, contractor, commission agreements | gap-correct | `employment_register_json`=`[]` so `score_legal()` is `gap-correct` (empty register, not a short employee list). Independent: 0 employment-agreement / offer-letter / restricted-stock / founder-agreement hits; Employee Attrition Analysis is KPI_OPS headcount, not an agreement. POC: corpus gap. |
| founder | Founder / key employee agreements | partial | No `agreement_class`=`founder_key` row. `score_legal()` maps missing founder to `partial` even when the employment register is empty. CIM has an Executive Leadership Team section (p.38) but no founder/key-employee *agreement* file. Rubric does not offer `gap-correct` for this item. |
| litigation | Litigation exposure | gap-correct | `litigation_register_json`=`[]`. Independent: 0 litigation / lawsuit / legal-proceeding hits. Diligence p.6 "Legal entity structure" is an org chart (Clearsulting LLC USA) not a matters schedule. POC: corpus gap. |
| privacy | Data privacy / security obligations | partial | `privacy_security_register_json`=`[]` (bar is >=5 rows for `pass`). Glossary false positives only (diligence p.54 "ADP" = Automated Data Processing). No Privacy Policy / BAA / DPA filenames. `score_legal()` has no `gap-correct` branch here, so empty is `partial`. |
| ip | IP ownership, assignment, OSS | gap-correct | `ip_register_json`=`[]` so `score_legal()` is `gap-correct`. CIM p.75-78 "Intellectual Property Deep Dive" describes product IP (Finance Insight Toolkit, OneStream-to-Workiva connector, Intercompany Analyzer) not assignment deeds or OSS policy. No IP-assignment / OSS-policy filenames. POC: corpus gap for legal IP instruments; product-IP marketing is not an assignment register. |
| insurance | Insurance coverage gaps | partial | `insurance_register_json`=`[]` (bar is >=3 rows for `pass`). Diligence "insurance" hits are payroll-related expense and certificates of *deposit*, not COI/policies. No Insurance / COI filenames. `score_legal()` maps empty insurance to `partial`. |

**Summary:** 0 `pass`, 4 `partial`, 7 `gap-correct` — `score_legal()` **0/11**. Matches assessed count 0/11 and `section_confidence`=`low`.

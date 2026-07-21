# Golden Checklist — Elder Care Customer Quality Agent (M1)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `94da269968c1c1f014118f93c1c5b9ad7243bb1e` |
| **E2E timestamp** | `2026-07-08T17:03:46Z` |
| **source table** | `uc13.analysis.customer_quality` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |

**Verdict key:** `pass` — field populated with citation-backed extraction; `partial` — field partially populated or cited from indirect source; `gap-correct` — absence or limitation correctly surfaced in `discrepancies_json` / structured nulls; `n/a` — not applicable to this corpus.

**Structural / integration note (not a scored row):** `contract_trigger_list` is populated post-LLM by `_build_contract_trigger_list` for any customer >20% of revenue; when non-empty, entries are consumed downstream by `legal_contracts_agent.py` for contract review. Elder Care run has an empty `contract_trigger_list` (no named customer exceeds the 20% trigger; `top_customers_json` is empty).

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| concentration | Customer concentration extraction | gap-correct | `top_customers_json`=[]; `concentration_summary_json` all null. `discrepancies_json` documents absent individual customer revenue data; client counts by geography cited separately but not scored as concentration. |
| retention | Retention metrics extraction | gap-correct | `retention_json` NRR/GRR/churn all null; `discrepancies_json` notes neither NRR nor GRR stated in retrieved corpus. No threshold verdict rendered (G2 owned by `test_cqa_thresholds.py`). |
| customer_tenure | Customer tenure extraction | pass | `customer_tenure_json.tenure_distribution_note` populated with Length-of-Stay distribution (57% 4+ years) from `2024 Elder Care - CIM_vF.pdf` p.44; citation `customer_tenure.tenure_distribution_note`, confidence high. |
| payor_mix | Payor mix extraction | partial | `payor_mix_json` has Private Pay 64%, Medicaid 11%, LTCI 11%, VA 7%, Other 7% (source: Phase 2 `revenue_model_note`, medium-confidence citation); Medicare, Commercial, and Managed Care null. `discrepancies_json` flags absent healthcare overlay categories. |
| discrepancies_json | Discrepancies correctly reported | pass | Five structured discrepancy entries covering concentration, retention, ACV, and payor-mix absences/limitations; aligns with null extraction fields and executive summary narrative. |
| data_room_gaps | Data-room gaps correctly reported | pass | `data_room_gaps`=[] — consistent with healthcare-overlay flag path (`government_payor_concentration` Yellow flag at 82% govt payor sum) and no contract-trigger gap entries (empty `contract_trigger_list`). Extraction absences captured in `discrepancies_json` rather than duplicate gap strings. |

**Summary:** 3 `pass`, 1 `partial`, 2 `gap-correct`, 0 `n/a`

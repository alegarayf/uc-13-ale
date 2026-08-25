# Golden Checklist — GKF Customer Quality Agent (CQA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `GKF` |
| **pipeline run_id** | `cd3abe7b4c3b4b9a91ffa977c5d2c1ce` (pipeline agent manifest; correlated to CQA analysis row `2026-08-19 19:16:50`) |
| **source table** | `uc13_ale.analysis.customer_quality` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_cqa()` (6-field; pass / partial / gap-correct) |
| **authoring provenance** | queried `uc13_ale.analysis.customer_quality` WHERE `company_name='GKF'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:16:50.517657 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `gap-correct` — absence correctly surfaced (empty concentration list, all-null retention with discrepancies, or valueless payor dict). GKF G1 floor is informational (`BASELINES["gkf"]` unset).

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| concentration | Customer concentration extraction | pass | `top_customers_json` is a nonempty 4-row list, so `score_cqa()` is `pass`. Named rows are school/location entities (Top Farm, Smart Kids, Tysons Kids, Ellicott City), not family customers. CIM p.2 disclaimer lists Creative Learning, Top Farm, Smart Kids, Bethesda Kids, and Tysons Kids as the Company. Databook OPEX sheet labels `Top Farm` / `Smart Kids` / `Tysons Kids` expense entities. Agent discrepancies already flag that no family-level concentration table exists. |
| retention | Retention metrics extraction | gap-correct | `retention_json.nrr_pct`, `grr_pct`, and `logo_churn_pct` are all null, and `discrepancies_json` is present, so `score_cqa()` takes the all-null `gap-correct` branch. Independent `ingestion.chunks` scan for GKF (`net revenue retention` / `nrr` / `gross revenue retention` / `logo churn`) returned 0 rows. |
| customer_tenure | Customer tenure extraction | pass | `customer_tenure_json.tenure_distribution_note` is nonempty (`~3 years`; enroll from 6 weeks through kindergarten). CIM p.53 COMPANY DEMOGRAPHICS BY THE NUMBERS: `~3 Years Avg. Student Tenure`. CIM p.14 Multi-Year Relationships with Families: students enroll from 6 weeks through kindergarten; `$177k` potential LTV. |
| payor_mix | Payor mix extraction | partial | `payor_mix_json` is a 1-row list (`Other`) with `pct_of_revenue` null. List-without-values is `partial` (not `gap-correct`). Correct for this corpus: CIM / databook are private-pay tuition, not a Medicare/Medicaid/VA mix. |
| discrepancies_json | Discrepancies correctly reported | pass | 3 `discrepancies_json` entries (school entities vs family concentration; NRR/GRR absent; healthcare payor mix not applicable). Meets `len >= 3`. |
| data_room_gaps | Data-room gaps correctly reported | pass | 2 `data_room_gaps` strings (T4C not determinable; CoC not determinable). List type meets `score_cqa()`. |

**Summary:** 4 `pass`, 1 `partial`, 1 `gap-correct` — `score_cqa()` **4/6**.

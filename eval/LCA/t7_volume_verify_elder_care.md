# T7 — Volume YAML verification (D1 / D4-A)

| Field | Value |
|-------|-------|
| **subtask** | T7 — Confirm Volume YAML artifacts exist post-E2E |
| **catalog** | `uc13_ale` (same as T4 D5-C run) |
| **company** | `Elder Care` (`sp_company_name`) |
| **E2E source** | T4 Cell 16 (`created_at` `2026-06-29T12:39:35Z`) |
| **verified_at** | `2026-06-29T18:45:00Z` (operator re-check via `_compare_baselines.py --json`) |
| **method** | `WorkspaceClient.files.download` (`.dev/legal_agent/_compare_baselines.py`) |

## Volume paths

| Path | Exists | Size (bytes) | Notes |
|------|--------|--------------|-------|
| `/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml` | **Y** | **22,300** | D1 normative deliverable — non-empty |
| `/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_contracts_report.yaml` | **Y** | **21,167** | D4-A legacy arm — non-empty |

**Kill criterion (normative missing/empty):** **NOT FIRED** — normative path present with 22,300 bytes.

## Normative `legal_report.yaml` — top-level keys

Outline check: **12/12** (`OUTLINE_OK`).

| Key | Present |
|-----|---------|
| `report` | Y |
| `confidence` | Y (`high`) |
| `executive_summary` | Y (246 chars) |
| `Customer & Vendor Contracts` | Y (contract_register=5, vendor_register=1) |
| `Platform & Channel Dependencies` | Y |
| `Employment & Founder Agreements` | Y (employment_register=2) |
| `Litigation & Disputes` | Y (litigation_register=1) |
| `IP, Privacy & Security` | Y (privacy_security_register=8) |
| `Insurance` | Y (insurance_register=4) |
| `Flags` | Y (8) |
| `Recommended Legal Diligence` | Y (1) |
| `Data Room Gaps` | Y (4) |

## Legacy `legal_contracts_report.yaml` — sample keys

| Key | Present / count |
|-----|-----------------|
| `report` | Y (`agent=legal_contracts`, `generated_at` matches T4 run) |
| `executive_summary` | Y (246 chars) |
| `contract_register` | Y (5) |
| `litigation_register` | Y (1) |
| `flags` | Y (8) |
| `data_room_gaps` | Y (4) |
| `citations` | Y (23) |

## Evidence command

```bash
python .dev/legal_agent/_compare_baselines.py --catalog uc13_ale --company "Elder Care" --json
```

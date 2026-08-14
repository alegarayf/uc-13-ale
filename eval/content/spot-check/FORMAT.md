# Spot-check presentation packet format (T4)

T4 chose **YAML** for presentation packets and operator verdict files. T5/T6 should name artifacts `{surface}_elder_care_<date>.md` for the human-readable rubric reference and `{surface}_elder_care_<date>.verdicts.yaml` for adjudication input to `write_spot_check_results`.

## Presentation packet (`*_presentation.yaml`)

Machine-readable claim enumeration for operator adjudication. Produced by `prepare_spot_check`.

```yaml
schema_version: 1
format: spot_check_presentation_v1
surface: exec_summary
company: Elder Care
company_slug: elder_care
source: uc13_ale.analysis.diligence_report.executive_summary
operator_id: null
prepared_at: '2026-08-12T18:00:00+00:00'
claim_count: 2
claims:
  - claim_id: exec.claim.001
    section: Business Overview
    claim_text: Example claim one.
    source_ref: source://uc13_ale.analysis.diligence_report.executive_summary#Business Overview
    source_doc: null
    source_location: null
    cited_chunk_id: null
    cited_locator_kind: null
    cited_locator_value: null
    verdict: null
    rationale: null
```

## Verdicts file (`*.verdicts.yaml`)

Operator-completed adjudication consumed by `write_spot_check_results`. Every enumerated `claim_id` must appear exactly once with a §16 verdict.

```yaml
schema_version: 1
surface: exec_summary
company: Elder Care
operator_id: operator_a
adjudicated_at: '2026-08-12T19:00:00+00:00'
claims:
  - claim_id: exec.claim.001
    verdict: supported
    rationale: null
  - claim_id: exec.claim.002
    verdict: contradicted
    rationale: Source text does not support the claim.
```

## Warehouse write semantics

- One `run_id` keys all claim rows and the completion marker (`write_spot_check_results`).
- Marker `writer` is `human_spot_check` (§16 vocabulary); `operator_id` lives in the verdicts artifact only.
- Registry guard-rail: surface must be assigned `human` in CHK-26a; any MVP surface assigned `judge` halts prepare/write.

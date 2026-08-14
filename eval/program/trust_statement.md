# Trust statement (generated — do not edit)

Generated: 2026-08-14T13:12:07.535543+00:00
Generator: v1
Catalog: uc13_ale
Companies: clearsulting, elder_care
Row count: 14
Comparison epoch baseline: baseline_acf58bcc4968
Ingestion snapshot: uc13_ale:55812:2026-08-11
Gold ready summary: 52 ready/partial + 5 annotated exclusions (no_citation_source)

## Rows

```yaml
- company: clearsulting
  layer: ingest_completeness
  surface: null
  attestation: attested
  reason: null
  method: sql_chunk_count
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: retrieval
  surface: null
  attestation: attested
  reason: null
  method: null
  rung: null
  evidence_refs:
  - baseline_acf58bcc4968
  - uc13_ale:55812:2026-08-11
  - signoffs/T4-refresh.md
  - signoffs/T5-baseline.md
  - eval/retrieval/reports/baseline_acf58bcc4968.json
  known_gaps:
  - 'Gold epoch: 52 ready/partial + 5 annotated exclusions (no_citation_source) (@
    uc13_ale:55812:2026-08-11)'
  manual_check: null
- company: clearsulting
  layer: agent_fields
  surface: null
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: e2e
  surface: null
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: content_correctness
  surface: fta_numeric
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: content_correctness
  surface: legal_register
  attestation: known_gap
  reason: corpus_absent
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: content_correctness
  surface: exec_summary
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: elder_care
  layer: ingest_completeness
  surface: null
  attestation: partial
  reason: incomplete_corpus
  method: sql_chunk_count
  rung: null
  evidence_refs: []
  known_gaps:
  - ingest completeness 98% (467/475 expected docs with chunks)
  - Elder Care ingest gap
  manual_check: null
- company: elder_care
  layer: retrieval
  surface: null
  attestation: attested
  reason: null
  method: null
  rung: null
  evidence_refs:
  - baseline_acf58bcc4968
  - uc13_ale:55812:2026-08-11
  - signoffs/T4-refresh.md
  - signoffs/T5-baseline.md
  - eval/retrieval/reports/baseline_acf58bcc4968.json
  known_gaps:
  - 'Gold epoch: 52 ready/partial + 5 annotated exclusions (no_citation_source) (@
    uc13_ale:55812:2026-08-11)'
  manual_check: null
- company: elder_care
  layer: agent_fields
  surface: null
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: elder_care
  layer: e2e
  surface: null
  attestation: not_attested
  reason: no_completed_run
  method: null
  rung: null
  evidence_refs: []
  known_gaps: []
  manual_check: null
- company: elder_care
  layer: content_correctness
  surface: fta_numeric
  attestation: attested
  reason: null
  method: null
  rung: human
  evidence_refs:
  - s2_scores:20260813T230816Z-0aed
  known_gaps: []
  manual_check: null
- company: elder_care
  layer: content_correctness
  surface: legal_register
  attestation: partial
  reason: claim_failures
  method: null
  rung: deterministic
  evidence_refs:
  - s2_scores:20260813T183720Z-r3f
  known_gaps:
  - 20/23 claims failed on legal_register
  manual_check: null
- company: elder_care
  layer: content_correctness
  surface: exec_summary
  attestation: partial
  reason: claim_failures
  method: null
  rung: human
  evidence_refs:
  - s2_scores:20260813T185002Z-5a1b
  known_gaps:
  - 3/53 claims failed on exec_summary
  manual_check: null
```

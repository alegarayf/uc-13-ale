# Trust statement (generated — do not edit)

Generated: 2026-08-18T23:14:04.561747+00:00
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
  attestation: partial
  reason: incomplete_agent_matrix
  method: null
  rung: null
  evidence_refs:
  - fta:6e1b4f5d95284b33bbd08942b3595dd6
  - legal:9d39d36f15204632b23c563305fcb916
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: e2e
  surface: null
  attestation: partial
  reason: incomplete_agent_matrix
  method: null
  rung: null
  evidence_refs:
  - fta:6e1b4f5d95284b33bbd08942b3595dd6
  - legal:9d39d36f15204632b23c563305fcb916
  known_gaps: []
  manual_check: null
- company: clearsulting
  layer: content_correctness
  surface: fta_numeric
  attestation: partial
  reason: claim_failures
  method: null
  rung: human
  evidence_refs:
  - s2_scores:20260818T231325Z-0a7e
  known_gaps:
  - 276/276 claims failed on fta_numeric
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
  attestation: partial
  reason: claim_failures
  method: null
  rung: human
  evidence_refs:
  - s2_scores:20260818T231317Z-c894
  known_gaps:
  - 52/53 claims failed on exec_summary
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
  attestation: attested
  reason: null
  method: null
  rung: null
  evidence_refs:
  - fta:5fef915601574dc3be629546910ba71e
  - legal:f45014f9dc7b473f8068d6695627460e
  - bma:2855aef9c0fb46e1b2252875d843ef3a
  - cqa:47f7f619821c445ca7161fdd97c9d3e5
  - kpi:093d0d03181941879a18f31a29d235ac
  - qoe:6ac6bfd73d864c3c9d038d13cb8e5be3
  - profiler:bddb1d187b284e0a8d22d420c2463727
  known_gaps: []
  manual_check: null
- company: elder_care
  layer: e2e
  surface: null
  attestation: attested
  reason: null
  method: null
  rung: null
  evidence_refs:
  - fta:5fef915601574dc3be629546910ba71e
  - legal:f45014f9dc7b473f8068d6695627460e
  - bma:2855aef9c0fb46e1b2252875d843ef3a
  - cqa:47f7f619821c445ca7161fdd97c9d3e5
  - kpi:093d0d03181941879a18f31a29d235ac
  - qoe:6ac6bfd73d864c3c9d038d13cb8e5be3
  - profiler:bddb1d187b284e0a8d22d420c2463727
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

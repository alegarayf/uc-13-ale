# Suite-gate waivers

## 2026-09-01-ledger-close-now-slice (audit remediation)

| Field | Value |
|---|---|
| Audit id | `2026-09-01-ledger-close-now-slice` |
| Audit date | 2026-09-01 |
| Closed plan | `ledger-close-now-slice` |
| Closed-plan closure SHA | `c4717111502172e0cf3639855b6eae1209557106` |
| Attribution baseline SHA | `b5c3c1454dcbf58de96e5d77d2ef4a0020ba62b2` |

### Waived pytest nodeids (exact `::test_*` suffix identity)

The following six nodeids are **pre-existing failures** at the attribution baseline. They are explicitly waived for the ledger-close-now-audit-remediation suite gate only:

- `test_committed_calibration_samples_pass_schema`
- `test_populated_artifacts_pass_item_2a_validators`
- `test_committed_store_validates`
- `test_committed_elder_care_yaml_validates_and_covers_registry`
- `test_prefix_resolution_ambiguous_raises`
- `test_ambiguous_tab_match_raises`

### Scope of waiver

The closed plan `ledger-close-now-slice` subtasks T10 and T10-tris carried kill criterion 3: **do not hand off with red tests**. That criterion is **explicitly waived for the six nodeids listed above only**, per audit `2026-09-01-ledger-close-now-slice` findings F0 and F1b. Remediation is documentation of pre-existing failures, not a code fix to the underlying causes (calibration HALT-25 keys, `GAP-M5-*` disposition vocabulary, exemption-count pin, gold-snapshot pin, Excel-tab matching).

This waiver **does not** cover:

- Any failure in `eval/retrieval/tests/test_parking_lot_schema.py`
- Any other pytest failure, collection error, or nodeid not listed above

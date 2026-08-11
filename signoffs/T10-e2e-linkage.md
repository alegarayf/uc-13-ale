# T10 sign-off — ops.e2e_linkage backfill (item 21)

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.0 · **Date:** 2026-08-11 · **Status:** complete

## DDL apply (statement-level)

Applied **only** the new table statement from `eval/retrieval/scripts/apply_ops_ddl.sql` (no full-file apply; M0 grant-drop caution honored).

```sql
CREATE TABLE IF NOT EXISTS uc13_ale.ops.e2e_linkage (
    run_id STRING NOT NULL,
    e2e_agent_id STRING NOT NULL,
    e2e_snapshot_table STRING NOT NULL,
    e2e_checklist_score INT NOT NULL,
    e2e_checklist_total INT NOT NULL,
    linked_at TIMESTAMP NOT NULL
) USING DELTA;
```

## Backfill

| Metric | Value |
|---|---|
| Source rows (`retrieval_harness_runs.e2e_agent_id IS NOT NULL`) | 15 |
| Rows inserted (first run) | 15 |
| Target rows after backfill | 15 |
| Idempotent re-run | 0 additional inserts |

Backfill SQL (from `record_e2e_linkage._backfill_e2e_linkage_sql`):

```sql
INSERT INTO uc13_ale.ops.e2e_linkage (...)
SELECT r.run_id, r.e2e_agent_id, r.e2e_snapshot_table,
       r.e2e_checklist_score, r.e2e_checklist_total,
       COALESCE(r.completed_at, r.created_at) AS linked_at
FROM uc13_ale.ops.retrieval_harness_runs r
WHERE r.e2e_agent_id IS NOT NULL
  AND r.e2e_snapshot_table IS NOT NULL
  AND r.e2e_checklist_score IS NOT NULL
  AND r.e2e_checklist_total IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM uc13_ale.ops.e2e_linkage e
      WHERE e.run_id = r.run_id AND e.e2e_agent_id = r.e2e_agent_id
  );
```

## Golden-five gate (5/5 agents ≥ 1 row)

```sql
SELECT e2e_agent_id, COUNT(*) AS n
FROM uc13_ale.ops.e2e_linkage
WHERE e2e_agent_id IN ('bma', 'cqa', 'kpi', 'qoe', 'profiler')
GROUP BY e2e_agent_id
ORDER BY e2e_agent_id;
```

| e2e_agent_id | n |
|---|---|
| bma | 3 |
| cqa | 1 |
| kpi | 1 |
| profiler | 2 |
| qoe | 1 |

Gate representative run ids recorded in `decision-logs/T10.md`.

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Statement-level DDL only | PASS |
| Backfill complete; inserted == source | PASS (15/15) |
| Backfill idempotent on re-run | PASS |
| Golden-five gate green | PASS (5/5 agents) |
| Existing UPDATE path preserved | PASS (`test_record_e2e_linkage.py` green) |
| No historical run mutation | PASS (read-only SELECT backfill) |

## Suite

Hermetic tests: `test_record_e2e_linkage.py`, `test_readme_record_e2e_linkage_section.py` — see CHANGELOG entry for full-suite result.

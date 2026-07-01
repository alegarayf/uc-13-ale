-- UC13 RE² ops DDL — spec Appendix I (normative shapes)
-- Placeholder {catalog} replaced by apply_ops_ddl.py (default: uc13)

CREATE SCHEMA IF NOT EXISTS {catalog}.ops;

CREATE TABLE IF NOT EXISTS {catalog}.ops.retrieval_harness_runs (
    run_id STRING NOT NULL,
    run_type STRING NOT NULL,
    company_name STRING NOT NULL,
    catalog STRING NOT NULL,
    ingestion_snapshot STRING NOT NULL,
    registry_hash STRING NOT NULL,
    gold_snapshot STRING NOT NULL,
    git_sha STRING,
    git_branch STRING,
    pr_url STRING,
    hypothesis STRING,
    affected_intents ARRAY<STRING> NOT NULL,
    gated_intents ARRAY<STRING> NOT NULL,
    ablation_config STRING,
    ablation_arm STRING,
    baseline_ref_run_id STRING,
    store_backend STRING NOT NULL,
    harness_status STRING NOT NULL,
    intent_count INT NOT NULL,
    gate_pass BOOLEAN,
    fallback_rate DOUBLE,
    empty_rate DOUBLE,
    e2e_agent_id STRING,
    e2e_snapshot_table STRING,
    e2e_checklist_score INT,
    e2e_checklist_total INT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.ops.retrieval_harness_results (
    run_id STRING NOT NULL,
    intent_id STRING NOT NULL,
    agent_id STRING,
    eval_status STRING NOT NULL,
    eval_k INT,
    effective_k INT,
    recall_at_10 DOUBLE,
    precision_at_10 DOUBLE,
    basis_conflict_at_10 DOUBLE,
    mrr DOUBLE,
    result_count INT NOT NULL,
    mode STRING,
    negatives_in_top_3 INT,
    ablation_arm STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.ops.retrieval_harness_deltas (
    run_id STRING NOT NULL,
    baseline_ref_run_id STRING NOT NULL,
    intent_id STRING NOT NULL,
    metric STRING NOT NULL,
    before DOUBLE NOT NULL,
    after DOUBLE NOT NULL,
    delta DOUBLE NOT NULL,
    gate_pass BOOLEAN NOT NULL,
    in_gated_scope BOOLEAN NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.ops.retrieval_provenance (
    run_id STRING NOT NULL,
    intent_id STRING NOT NULL,
    company_name STRING NOT NULL,
    catalog STRING NOT NULL,
    query STRING NOT NULL,
    mode STRING NOT NULL,
    chunk_id STRING NOT NULL,
    rank INT NOT NULL,
    sim_score DOUBLE NOT NULL,
    merge_score DOUBLE NOT NULL,
    tier INT NOT NULL,
    section_header STRING NOT NULL,
    file_name STRING NOT NULL,
    source_type STRING NOT NULL,
    chars_allocated INT,
    context_section STRING,
    created_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE OR REPLACE VIEW {catalog}.ops.retrieval_harness_latest_baseline AS
SELECT *
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY company_name, catalog
            ORDER BY completed_at DESC
        ) AS rn
    FROM {catalog}.ops.retrieval_harness_runs
    WHERE run_type = 'baseline' AND harness_status = 'complete'
) t
WHERE rn = 1;

CREATE OR REPLACE VIEW {catalog}.ops.v_retrieval_harness_delta AS
SELECT
    cur.run_id,
    r.baseline_ref_run_id,
    cur.intent_id,
    b.recall_at_10 AS recall_before,
    cur.recall_at_10 AS recall_after,
    cur.recall_at_10 - b.recall_at_10 AS recall_delta
FROM {catalog}.ops.retrieval_harness_results cur
JOIN {catalog}.ops.retrieval_harness_runs r ON r.run_id = cur.run_id
JOIN {catalog}.ops.retrieval_harness_results b
    ON b.run_id = r.baseline_ref_run_id AND b.intent_id = cur.intent_id
WHERE r.baseline_ref_run_id IS NOT NULL;

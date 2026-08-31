-- S2 score table — spec §8.8 logical field set, §9 storage layer
-- Catalog pinned to uc13_ale (dev/eval); production uses uc13 per databricks/CLAUDE.md
-- Applied via SDK statement_execution (T1); {catalog} placeholder for reuse

CREATE SCHEMA IF NOT EXISTS {catalog}.eval;

CREATE TABLE IF NOT EXISTS {catalog}.eval.s2_scores (
    company STRING NOT NULL,
    surface STRING NOT NULL,
    run_id STRING NOT NULL,
    run_ts TIMESTAMP NOT NULL,
    row_type STRING NOT NULL,
    claim_id STRING,
    verdict STRING,
    rationale STRING,
    writer STRING,
    asserted_magnitude DECIMAL(38, 9),
    asserted_unit STRING,
    extracted_magnitude DECIMAL(38, 9),
    extracted_unit STRING,
    cited_chunk_id STRING,
    cited_locator_kind STRING,
    cited_locator_value STRING,
    judge_verdict_advisory STRING
) USING DELTA;

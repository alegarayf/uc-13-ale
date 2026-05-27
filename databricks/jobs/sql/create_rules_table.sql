-- Garden rules table for Rallyday CRUD APIs.
-- In Unity Catalog, qualify as <catalog>.garden.rules (see DATABRICKS_CATALOG / DATABRICKS_SCHEMA).

CREATE TABLE IF NOT EXISTS garden.rules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name STRING,
    description STRING,
    status STRING CHECK (status IN ('active', 'inactive')),
    rule_source STRING CHECK (rule_source IN ('form', 'ai')),
    nl_prompt STRING,
    nl_summary STRING,
    rule_definition STRING,
    python_source STRING,
    python_entrypoint STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_updated_by STRING
);

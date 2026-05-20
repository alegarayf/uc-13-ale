-- Garden rules table for Rallyday CRUD APIs.
-- In Unity Catalog, qualify as <catalog>.garden.rules (see DATABRICKS_CATALOG / DATABRICKS_SCHEMA).

CREATE TABLE IF NOT EXISTS garden.rules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name STRING,
    description STRING,
    comparison STRING CHECK (comparison IN ('=', '<', '>', '<=', '>=')),
    minimum INT,
    maximum INT,
    uom STRING,
    status STRING CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_updated_by STRING
);

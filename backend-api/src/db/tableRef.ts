import type { DatabricksStoreConfig } from "../stores/databricksStore.js";

/** Fully qualified Unity Catalog table name: catalog.schema.table */
export function rulesTableRef(cfg: Pick<DatabricksStoreConfig, "catalog" | "schema">): string {
  const catalog = cfg.catalog.trim();
  const schema = cfg.schema.trim();
  if (!catalog || !schema) {
    throw new Error("DATABRICKS_CATALOG and DATABRICKS_SCHEMA are required for Databricks queries");
  }
  return `${catalog}.${schema}.rules`;
}

/** Unity Catalog materialized view for Salesforce opportunities (silver layer). */
export function opportunitySilverTableRef(): string {
  return "salesforce_silver.opportunity_silver";
}

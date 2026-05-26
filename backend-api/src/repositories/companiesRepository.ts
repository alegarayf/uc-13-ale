import type { DatabricksClient } from "../db/databricksClient.js";
import { opportunitySilverTableRef } from "../db/tableRef.js";
import type { Company } from "../types/company.js";
import { MEMORY_SEED_COMPANIES } from "./companiesSeedData.js";
import {
  mapRowToCompany,
  OPPORTUNITY_SELECT_COLUMNS,
} from "./companyRowMapper.js";

export interface CompaniesRepository {
  findByOwnerEmail(ownerEmail: string): Promise<Company[]>;
  findById(id: string): Promise<Company | null>;
}

export function createMemoryCompaniesRepository(): CompaniesRepository {
  const companies = new Map(MEMORY_SEED_COMPANIES.map((c) => [c.id, c]));

  return {
    async findByOwnerEmail(ownerEmail) {
      const normalized = ownerEmail.trim().toLowerCase();
      return [...companies.values()]
        .filter(
          (c) =>
            (c.opportunity_owner_email ?? "").trim().toLowerCase() === normalized,
        )
        .sort((a, b) => a.project_name.localeCompare(b.project_name));
    },

    async findById(id) {
      return companies.get(id) ?? null;
    },
  };
}

export function createDatabricksCompaniesRepository(
  db: DatabricksClient,
): CompaniesRepository {
  const table = opportunitySilverTableRef();

  return {
    async findByOwnerEmail(ownerEmail) {
      const rows = await db.query(
        `SELECT ${OPPORTUNITY_SELECT_COLUMNS}
         FROM ${table}
         WHERE OpportunityOwnerEmail = :ownerEmail
         ORDER BY ProjectName`,
        { ownerEmail },
      );
      return rows.map(mapRowToCompany);
    },

    async findById(id) {
      const rows = await db.query(
        `SELECT ${OPPORTUNITY_SELECT_COLUMNS}
         FROM ${table}
         WHERE Id = :id`,
        { id },
      );
      if (!rows.length) return null;
      return mapRowToCompany(rows[0]!);
    },
  };
}

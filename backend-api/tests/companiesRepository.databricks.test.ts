import { describe, expect, it, vi } from "vitest";
import { createDatabricksCompaniesRepository } from "../src/repositories/companiesRepository.js";
import { OPPORTUNITY_SELECT_COLUMNS } from "../src/repositories/companyRowMapper.js";
import type { DatabricksClient } from "../src/db/databricksClient.js";

const sampleRow = {
  Id: "006ABC",
  ProjectName: "Acme Rollout",
  AccountName: "Acme Corp",
  Industry: "Technology",
  AnnualRevenue: 1_000_000,
  EmployeeHeadCount: 10,
  YearFounded: 2015,
  EBITDA: 200_000,
  EBITDAMargin: 0.2,
  DaysSinceLastActivity: 1,
  Website: "https://acme.example",
  SourceScrubUrl: null,
  LinkedInCompanyId: null,
  ZoomInfoCompanyId: null,
  GrowthRate12Months: null,
  GrowthRate9Months: null,
  GrowthRate6Months: null,
  Investors: null,
  Name: "Acme",
  Description: null,
  StageName: "Proposal",
  Type: "New Business",
  LeadSource: "Web",
  OpportunityOwner: "Matt Crysler",
  OpportunityOwnerRole: "MD",
  OpportunityOwnerEmail: "mcrysler@nimblegravity.com",
  Status: "Open",
};

function mockClient(handlers: {
  onQuery?: (sql: string, params?: Record<string, unknown>) => Record<string, unknown>[];
}): DatabricksClient {
  return {
    ping: vi.fn(),
    close: vi.fn(),
    query: vi.fn(async (sql, params) => {
      if (handlers.onQuery) return handlers.onQuery(sql, params);
      return [];
    }),
  };
}

describe("createDatabricksCompaniesRepository", () => {
  it("queries opportunity silver view filtered by owner on list", async () => {
    const db = mockClient({
      onQuery: (sql, params) => {
        expect(sql).toContain("salesforce_silver.opportunity_silver");
        expect(sql).toContain(OPPORTUNITY_SELECT_COLUMNS);
        expect(sql).toContain("OpportunityOwnerEmail = :ownerEmail");
        expect(sql).toContain("ORDER BY ProjectName");
        expect(params).toEqual({ ownerEmail: "mcrysler@nimblegravity.com" });
        return [sampleRow];
      },
    });
    const repo = createDatabricksCompaniesRepository(db);
    const companies = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(companies).toHaveLength(1);
    expect(companies[0]!.project_name).toBe("Acme Rollout");
    expect(db.query).toHaveBeenCalledTimes(1);
  });

  it("queries by Id on findById", async () => {
    const db = mockClient({
      onQuery: (sql, params) => {
        expect(sql).toContain("WHERE Id = :id");
        expect(params).toEqual({ id: "006ABC" });
        return [sampleRow];
      },
    });
    const repo = createDatabricksCompaniesRepository(db);
    const company = await repo.findById("006ABC");
    expect(company?.id).toBe("006ABC");
    expect(company?.account_name).toBe("Acme Corp");
  });

  it("returns null when findById has no rows", async () => {
    const db = mockClient({ onQuery: () => [] });
    const repo = createDatabricksCompaniesRepository(db);
    expect(await repo.findById("missing")).toBeNull();
  });
});

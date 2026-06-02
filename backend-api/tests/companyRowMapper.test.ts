import { describe, expect, it } from "vitest";
import {
  mapRowToCompany,
  mapRowToCompanyFields,
  OPPORTUNITY_SELECT_COLUMNS,
} from "../src/repositories/companyRowMapper.js";
import { Company } from "../src/types/company.js";

const fullRow = {
  Id: "006ABC",
  ProjectName: "Acme Rollout",
  AccountName: "Acme Corp",
  Industry: "Technology",
  AnnualRevenue: 12_500_000,
  EmployeeHeadCount: 450,
  YearFounded: 2001,
  EBITDA: 2_100_000,
  EBITDAMargin: 0.168,
  DaysSinceLastActivity: 2,
  Website: "https://acme.example",
  SourceScrubUrl: "https://scrub.example/acme",
  LinkedInCompanyId: "acme-corp",
  ZoomInfoCompanyId: "ZI-99",
  GrowthRate12Months: 0.14,
  GrowthRate9Months: 0.11,
  GrowthRate6Months: 0.07,
  Investors: "Fund A; Fund B",
  Name: "Acme Platform",
  Description: "Full platform migration.",
  StageName: "Proposal",
  Type: "New Business",
  LeadSource: "Web",
  OpportunityOwner: "Matt Crysler",
  OpportunityOwnerRole: "MD",
  OpportunityOwnerEmail: "owner@example.com",
  Status: "Open",
};

describe("mapRowToCompanyFields", () => {
  it("maps full PascalCase Salesforce row", () => {
    const fields = mapRowToCompanyFields(fullRow);
    expect(fields).toMatchObject({
      id: "006ABC",
      project_name: "Acme Rollout",
      account_name: "Acme Corp",
      industry: "Technology",
      annual_revenue: 12_500_000,
      employee_head_count: 450,
      year_founded: 2001,
      ebitda: 2_100_000,
      ebitda_margin: 0.168,
      days_since_last_activity: 2,
      website: "https://acme.example",
      source_scrub_url: "https://scrub.example/acme",
      linked_in_company_id: "acme-corp",
      zoom_info_company_id: "ZI-99",
      growth_rate_12_months: 0.14,
      growth_rate_9_months: 0.11,
      growth_rate_6_months: 0.07,
      investors: "Fund A; Fund B",
      name: "Acme Platform",
      description: "Full platform migration.",
      stage_name: "Proposal",
      type: "New Business",
      lead_source: "Web",
      opportunity_owner: "Matt Crysler",
      opportunity_owner_role: "MD",
      opportunity_owner_email: "owner@example.com",
      status: "Open",
    });
  });

  it("maps snake_case columns", () => {
    const fields = mapRowToCompanyFields({
      id: "opp-1",
      project_name: "Beta",
      account_name: "Beta LLC",
      annual_revenue: null,
      employee_head_count: null,
      industry: null,
      status: "Open",
      opportunity_owner_email: "user@test.com",
    });
    expect(fields.project_name).toBe("Beta");
    expect(fields.annual_revenue).toBeNull();
  });

  it("uses fallbacks when name fields are empty", () => {
    const fields = mapRowToCompanyFields({ Id: "x" });
    expect(fields.project_name).toBe("Untitled project");
    expect(fields.account_name).toBe("—");
  });

  it("mapRowToCompany returns a Company instance", () => {
    const company = mapRowToCompany(fullRow);
    expect(company).toBeInstanceOf(Company);
    expect(company.annual_revenue).toBe(12_500_000);
  });

  it("exports all silver view columns in SELECT list", () => {
    expect(OPPORTUNITY_SELECT_COLUMNS).toContain("AnnualRevenue");
    expect(OPPORTUNITY_SELECT_COLUMNS).toContain("OpportunityOwnerRole");
    expect(OPPORTUNITY_SELECT_COLUMNS).toContain("Description");
  });
});

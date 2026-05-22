import type { DatabricksClient } from "../db/databricksClient.js";
import { opportunitySilverTableRef } from "../db/tableRef.js";
import { Company, type CompanyFields } from "../types/company.js";
import {
  mapRowToCompany,
  OPPORTUNITY_SELECT_COLUMNS,
} from "./companyRowMapper.js";

export interface CompaniesRepository {
  findByOwnerEmail(ownerEmail: string): Promise<Company[]>;
  findById(id: string): Promise<Company | null>;
}

const SEED_OWNER = "mcrysler@nimblegravity.com";

const EMPTY_OPTIONAL: Omit<CompanyFields, "id" | "project_name" | "account_name"> = {
  industry: null,
  annual_revenue: null,
  employee_head_count: null,
  year_founded: null,
  ebitda: null,
  ebitda_margin: null,
  days_since_last_activity: null,
  website: null,
  source_scrub_url: null,
  linked_in_company_id: null,
  zoom_info_company_id: null,
  growth_rate_12_months: null,
  growth_rate_9_months: null,
  growth_rate_6_months: null,
  investors: null,
  name: null,
  description: null,
  stage_name: null,
  type: null,
  lead_source: null,
  opportunity_owner: null,
  opportunity_owner_role: null,
  opportunity_owner_email: null,
  status: null,
};

function seedCompany(
  fields: Pick<CompanyFields, "id" | "project_name" | "account_name"> &
    Partial<CompanyFields>,
): Company {
  return new Company({
    ...EMPTY_OPTIONAL,
    opportunity_owner_email: SEED_OWNER,
    ...fields,
  });
}

const SEED_COMPANIES: Company[] = [
  seedCompany({
    id: "opp-001",
    project_name: "Northwind Expansion",
    account_name: "Northwind Traders",
    industry: "Manufacturing",
    annual_revenue: 45_000_000,
    employee_head_count: 320,
    year_founded: 1998,
    ebitda: 8_500_000,
    ebitda_margin: 0.189,
    days_since_last_activity: 4,
    website: "https://northwind.example.com",
    source_scrub_url: "https://sourcescrub.example.com/northwind",
    linked_in_company_id: "northwind-traders",
    zoom_info_company_id: "ZI-10001",
    growth_rate_12_months: 0.12,
    growth_rate_9_months: 0.09,
    growth_rate_6_months: 0.06,
    investors: "Summit Partners; River Capital",
    name: "Northwind Expansion Opportunity",
    description:
      "Expansion initiative to modernize ERP and enter two new regional markets.",
    stage_name: "Qualification",
    type: "New Business",
    lead_source: "Partner Referral",
    opportunity_owner: "Matt Crysler",
    opportunity_owner_role: "Managing Director",
    opportunity_owner_email: SEED_OWNER,
    status: "Open",
  }),
  seedCompany({
    id: "opp-002",
    project_name: "Contoso Platform",
    account_name: "Contoso Ltd",
    industry: "Technology",
    website: "https://contoso.example.com",
    stage_name: "Proposal",
    lead_source: "Web",
    status: "In Review",
    type: "Existing Customer",
    opportunity_owner: "Matt Crysler",
    opportunity_owner_role: "Managing Director",
  }),
  seedCompany({
    id: "opp-003",
    project_name: "Fabrikam Health",
    account_name: "Fabrikam Inc",
    industry: "Healthcare",
    website: "https://fabrikam.example.com",
    stage_name: "Negotiation",
    lead_source: "Conference",
    status: "Open",
  }),
  seedCompany({
    id: "opp-004",
    project_name: "Adventure Works Rollout",
    account_name: "Adventure Works",
    industry: "Retail",
    website: "https://adventureworks.example.com",
    stage_name: "Closed Won",
    lead_source: "Existing Customer",
    status: "Won",
    annual_revenue: 120_000_000,
    employee_head_count: 2400,
  }),
  seedCompany({
    id: "opp-005",
    project_name: "Tailspin Pilot",
    account_name: "Tailspin Toys",
    industry: "Consumer Goods",
    stage_name: "Discovery",
    lead_source: "Cold Outreach",
    status: "Open",
    days_since_last_activity: 21,
  }),
  seedCompany({
    id: "opp-999",
    project_name: "Other Owner Co",
    account_name: "Other Corp",
    industry: "Finance",
    website: "https://other.example.com",
    stage_name: "Qualification",
    lead_source: "Web",
    status: "Open",
    opportunity_owner_email: "other.user@example.com",
  }),
];

export function createMemoryCompaniesRepository(): CompaniesRepository {
  const companies = new Map(SEED_COMPANIES.map((c) => [c.id, c]));

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

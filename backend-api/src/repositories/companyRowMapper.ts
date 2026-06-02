import { Company, type CompanyFields } from "../types/company.js";

function pickField(row: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (key in row) return row[key];
    const upper = key.toUpperCase();
    if (upper in row) return row[upper];
    const lower = key.toLowerCase();
    if (lower in row) return row[lower];
  }
  return undefined;
}

function toNullableString(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function toRequiredString(value: unknown, fallback = ""): string {
  if (value == null || value === "") return fallback;
  return String(value);
}

function toNullableNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export const OPPORTUNITY_SELECT_COLUMNS = [
  "Id",
  "ProjectName",
  "AccountName",
  "Industry",
  "AnnualRevenue",
  "EmployeeHeadCount",
  "YearFounded",
  "EBITDA",
  "EBITDAMargin",
  "DaysSinceLastActivity",
  "Website",
  "SourceScrubUrl",
  "LinkedInCompanyId",
  "ZoomInfoCompanyId",
  "GrowthRate12Months",
  "GrowthRate9Months",
  "GrowthRate6Months",
  "Investors",
  "Name",
  "Description",
  "StageName",
  "Type",
  "LeadSource",
  "OpportunityOwner",
  "OpportunityOwnerRole",
  "OpportunityOwnerEmail",
  "Status",
].join(", ");

export function mapRowToCompanyFields(row: Record<string, unknown>): CompanyFields {
  const id = pickField(row, ["Id", "id", "opportunity_id", "OpportunityId"]);
  return {
    id: toRequiredString(id, ""),
    project_name: toRequiredString(
      pickField(row, ["ProjectName", "Project_Name", "project_name"]),
      "Untitled project",
    ),
    account_name: toRequiredString(
      pickField(row, ["AccountName", "Account_Name", "account_name"]),
      "—",
    ),
    industry: toNullableString(pickField(row, ["Industry", "industry"])),
    annual_revenue: toNullableNumber(
      pickField(row, ["AnnualRevenue", "annual_revenue"]),
    ),
    employee_head_count: toNullableNumber(
      pickField(row, ["EmployeeHeadCount", "employee_head_count"]),
    ),
    year_founded: toNullableNumber(pickField(row, ["YearFounded", "year_founded"])),
    ebitda: toNullableNumber(pickField(row, ["EBITDA", "ebitda"])),
    ebitda_margin: toNullableNumber(
      pickField(row, ["EBITDAMargin", "ebitda_margin"]),
    ),
    days_since_last_activity: toNullableNumber(
      pickField(row, ["DaysSinceLastActivity", "days_since_last_activity"]),
    ),
    website: toNullableString(pickField(row, ["Website", "website"])),
    source_scrub_url: toNullableString(
      pickField(row, ["SourceScrubUrl", "source_scrub_url"]),
    ),
    linked_in_company_id: toNullableString(
      pickField(row, ["LinkedInCompanyId", "linked_in_company_id"]),
    ),
    zoom_info_company_id: toNullableString(
      pickField(row, ["ZoomInfoCompanyId", "zoom_info_company_id"]),
    ),
    growth_rate_12_months: toNullableNumber(
      pickField(row, ["GrowthRate12Months", "growth_rate_12_months"]),
    ),
    growth_rate_9_months: toNullableNumber(
      pickField(row, ["GrowthRate9Months", "growth_rate_9_months"]),
    ),
    growth_rate_6_months: toNullableNumber(
      pickField(row, ["GrowthRate6Months", "growth_rate_6_months"]),
    ),
    investors: toNullableString(pickField(row, ["Investors", "investors"])),
    name: toNullableString(pickField(row, ["Name", "name"])),
    description: toNullableString(pickField(row, ["Description", "description"])),
    stage_name: toNullableString(
      pickField(row, ["StageName", "Stage_Name", "stage_name"]),
    ),
    type: toNullableString(pickField(row, ["Type", "type"])),
    lead_source: toNullableString(
      pickField(row, ["LeadSource", "Lead_Source", "lead_source"]),
    ),
    opportunity_owner: toNullableString(
      pickField(row, ["OpportunityOwner", "opportunity_owner"]),
    ),
    opportunity_owner_role: toNullableString(
      pickField(row, ["OpportunityOwnerRole", "opportunity_owner_role"]),
    ),
    opportunity_owner_email: toNullableString(
      pickField(row, [
        "OpportunityOwnerEmail",
        "Opportunity_Owner_Email",
        "opportunity_owner_email",
      ]),
    ),
    status: toNullableString(pickField(row, ["Status", "status"])),
  };
}

export function mapRowToCompany(row: Record<string, unknown>): Company {
  return new Company(mapRowToCompanyFields(row));
}

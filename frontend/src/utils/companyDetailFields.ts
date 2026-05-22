import type { Company } from "../types/company.js";

export type CompanyDetailFormat =
  | "text"
  | "url"
  | "status"
  | "mono"
  | "currency"
  | "percent"
  | "integer"
  | "decimal"
  | "multiline";

export interface CompanyDetailField {
  key: keyof Company;
  label: string;
  format?: CompanyDetailFormat;
}

/** Flat list of every field in the opportunity silver schema (API snake_case keys). */
export const COMPANY_DETAIL_FIELDS: CompanyDetailField[] = [
  { key: "id", label: "Id", format: "mono" },
  { key: "project_name", label: "Project name" },
  { key: "account_name", label: "Account name" },
  { key: "industry", label: "Industry" },
  { key: "annual_revenue", label: "Annual revenue", format: "currency" },
  { key: "employee_head_count", label: "Employee head count", format: "integer" },
  { key: "year_founded", label: "Year founded", format: "integer" },
  { key: "ebitda", label: "EBITDA", format: "currency" },
  { key: "ebitda_margin", label: "EBITDA margin", format: "percent" },
  { key: "days_since_last_activity", label: "Days since last activity", format: "decimal" },
  { key: "website", label: "Website", format: "url" },
  { key: "source_scrub_url", label: "Source scrub URL", format: "url" },
  { key: "linked_in_company_id", label: "LinkedIn company id", format: "mono" },
  { key: "zoom_info_company_id", label: "ZoomInfo company id", format: "mono" },
  { key: "growth_rate_12_months", label: "Growth rate (12 months)", format: "percent" },
  { key: "growth_rate_9_months", label: "Growth rate (9 months)", format: "percent" },
  { key: "growth_rate_6_months", label: "Growth rate (6 months)", format: "percent" },
  { key: "investors", label: "Investors" },
  { key: "name", label: "Name" },
  { key: "description", label: "Description", format: "multiline" },
  { key: "stage_name", label: "Stage name" },
  { key: "type", label: "Type" },
  { key: "lead_source", label: "Lead source" },
  { key: "opportunity_owner", label: "Opportunity owner" },
  { key: "opportunity_owner_role", label: "Opportunity owner role" },
  { key: "opportunity_owner_email", label: "Opportunity owner email" },
  { key: "status", label: "Status", format: "status" },
];

const ALL_COMPANY_KEYS = Object.keys({
  id: "",
  project_name: "",
  account_name: "",
  industry: "",
  annual_revenue: 0,
  employee_head_count: 0,
  year_founded: 0,
  ebitda: 0,
  ebitda_margin: 0,
  days_since_last_activity: 0,
  website: "",
  source_scrub_url: "",
  linked_in_company_id: "",
  zoom_info_company_id: "",
  growth_rate_12_months: 0,
  growth_rate_9_months: 0,
  growth_rate_6_months: 0,
  investors: "",
  name: "",
  description: "",
  stage_name: "",
  type: "",
  lead_source: "",
  opportunity_owner: "",
  opportunity_owner_role: "",
  opportunity_owner_email: "",
  status: "",
} satisfies Record<keyof Company, unknown>) as (keyof Company)[];

function assertAllKeysCovered(): void {
  const covered = new Set(COMPANY_DETAIL_FIELDS.map((f) => f.key));
  for (const key of ALL_COMPANY_KEYS) {
    if (!covered.has(key)) {
      throw new Error(`Company detail fields missing: ${String(key)}`);
    }
  }
  if (covered.size !== ALL_COMPANY_KEYS.length) {
    throw new Error("Company detail fields contain duplicate or extra keys");
  }
}

assertAllKeysCovered();

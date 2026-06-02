import { describe, expect, it } from "vitest";
import type { Company } from "../types/company.js";
import { COMPANY_DETAIL_FIELDS } from "./companyDetailFields.js";

const sample: Company = {
  id: "opp-1",
  project_name: "Acme",
  account_name: "Acme Corp",
  industry: "Tech",
  annual_revenue: 1_000_000,
  employee_head_count: 50,
  year_founded: 2010,
  ebitda: 250_000,
  ebitda_margin: 0.25,
  days_since_last_activity: 3.5,
  website: "https://acme.example",
  source_scrub_url: null,
  linked_in_company_id: "acme",
  zoom_info_company_id: null,
  growth_rate_12_months: 0.1,
  growth_rate_9_months: 0.08,
  growth_rate_6_months: 0.05,
  investors: "VC Fund",
  name: "Acme Deal",
  description: "Notes",
  stage_name: "Proposal",
  type: "New Business",
  lead_source: "Web",
  opportunity_owner: "Owner",
  opportunity_owner_role: "MD",
  opportunity_owner_email: "owner@example.com",
  status: "Open",
};

describe("COMPANY_DETAIL_FIELDS", () => {
  it("includes every Company field exactly once in schema order", () => {
    const keys = COMPANY_DETAIL_FIELDS.map((f) => f.key);
    const companyKeys = Object.keys(sample) as (keyof Company)[];
    expect(keys).toHaveLength(companyKeys.length);
    expect(new Set(keys).size).toBe(keys.length);
    for (const key of companyKeys) {
      expect(keys).toContain(key);
    }
  });

  it("maps schema labels for key financial fields", () => {
    const labels = Object.fromEntries(COMPANY_DETAIL_FIELDS.map((f) => [f.key, f.label]));
    expect(labels.annual_revenue).toBe("Annual revenue");
    expect(labels.ebitda_margin).toBe("EBITDA margin");
    expect(labels.opportunity_owner_email).toBe("Opportunity owner email");
  });
});

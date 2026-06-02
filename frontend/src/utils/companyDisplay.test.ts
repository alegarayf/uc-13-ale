import { describe, expect, it } from "vitest";
import type { Company } from "../types/company.js";
import { EMPTY_COMPANY_FILTERS } from "../types/company.js";
import {
  companySearchText,
  formatCompanyCurrency,
  formatCompanyDetailValue,
  formatCompanyField,
  formatCompanyNumber,
  formatCompanyPercent,
  matchesCompanyFilters,
  matchesCompanySearch,
  uniqueFilterValues,
} from "./companyDisplay.js";

const sample: Company = {
  id: "opp-1",
  project_name: "Acme Rollout",
  account_name: "Acme Corp",
  industry: "Technology",
  annual_revenue: 5_000_000,
  employee_head_count: 120,
  year_founded: 2005,
  ebitda: 1_000_000,
  ebitda_margin: 0.2,
  days_since_last_activity: 7,
  website: "https://acme.example",
  source_scrub_url: null,
  linked_in_company_id: "acme-corp",
  zoom_info_company_id: null,
  growth_rate_12_months: 0.15,
  growth_rate_9_months: null,
  growth_rate_6_months: null,
  investors: "Alpha Capital",
  name: "Acme Opportunity",
  description: "Enterprise rollout",
  stage_name: "Proposal",
  type: "New Business",
  lead_source: "Web",
  opportunity_owner: "Jane Doe",
  opportunity_owner_role: "Partner",
  opportunity_owner_email: "owner@example.com",
  status: "Open",
};

describe("formatCompanyField", () => {
  it("returns em dash for null and empty", () => {
    expect(formatCompanyField(null)).toBe("—");
    expect(formatCompanyField("")).toBe("—");
  });
});

describe("formatCompanyNumber", () => {
  it("formats integers and decimals", () => {
    expect(formatCompanyNumber(120)).toBe("120");
    expect(formatCompanyNumber(3.5)).toBe("3.5");
    expect(formatCompanyNumber(null)).toBe("—");
  });
});

describe("formatCompanyCurrency", () => {
  it("formats USD", () => {
    expect(formatCompanyCurrency(5_000_000)).toContain("5");
    expect(formatCompanyCurrency(null)).toBe("—");
  });
});

describe("formatCompanyPercent", () => {
  it("formats fractional rates as percent", () => {
    expect(formatCompanyPercent(0.2)).toBe("20%");
    expect(formatCompanyPercent(15)).toBe("15%");
  });
});

describe("formatCompanyDetailValue", () => {
  it("formats by field type", () => {
    expect(
      formatCompanyDetailValue(sample, {
        key: "annual_revenue",
        label: "Annual revenue",
        format: "currency",
      }),
    ).toContain("5");
    expect(
      formatCompanyDetailValue(sample, {
        key: "ebitda_margin",
        label: "EBITDA margin",
        format: "percent",
      }),
    ).toBe("20%");
  });
});

describe("matchesCompanySearch", () => {
  it("matches when query is empty", () => {
    expect(matchesCompanySearch(sample, "")).toBe(true);
  });

  it("matches across expanded fields", () => {
    expect(matchesCompanySearch(sample, "alpha capital")).toBe(true);
    expect(matchesCompanySearch(sample, "enterprise")).toBe(true);
    expect(matchesCompanySearch(sample, "nomatch")).toBe(false);
  });
});

describe("companySearchText", () => {
  it("includes investors and description", () => {
    expect(companySearchText(sample)).toContain("alpha capital");
    expect(companySearchText(sample)).toContain("enterprise rollout");
  });
});

describe("matchesCompanyFilters", () => {
  it("passes when all filters are empty", () => {
    expect(matchesCompanyFilters(sample, EMPTY_COMPANY_FILTERS)).toBe(true);
  });

  it("filters by each field", () => {
    expect(
      matchesCompanyFilters(sample, { ...EMPTY_COMPANY_FILTERS, industry: "Technology" }),
    ).toBe(true);
    expect(
      matchesCompanyFilters(sample, { ...EMPTY_COMPANY_FILTERS, industry: "Healthcare" }),
    ).toBe(false);
  });
});

describe("uniqueFilterValues", () => {
  it("returns sorted unique non-empty values", () => {
    const companies: Company[] = [
      sample,
      { ...sample, id: "2", industry: "Healthcare", status: "Won" },
    ];
    expect(uniqueFilterValues(companies, "industry")).toEqual(["Healthcare", "Technology"]);
  });
});

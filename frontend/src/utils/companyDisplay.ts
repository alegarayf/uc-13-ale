import type { Company, CompanyFiltersState } from "../types/company.js";
import type { CompanyDetailField, CompanyDetailFormat } from "./companyDetailFields.js";

export function formatCompanyField(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  return value;
}

export function formatCompanyNumber(
  value: number | null | undefined,
  options?: { maximumFractionDigits?: number },
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: options?.maximumFractionDigits ?? 2,
  });
}

export function formatCompanyCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function formatCompanyPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const display = Math.abs(value) <= 1 ? value * 100 : value;
  return `${display.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

export function formatCompanyDetailValue(
  company: Company,
  field: CompanyDetailField,
): string {
  const raw = company[field.key];
  const format: CompanyDetailFormat = field.format ?? "text";

  if (format === "currency") {
    return formatCompanyCurrency(raw as number | null);
  }
  if (format === "percent") {
    return formatCompanyPercent(raw as number | null);
  }
  if (format === "integer" || format === "decimal") {
    return formatCompanyNumber(raw as number | null, {
      maximumFractionDigits: format === "integer" ? 0 : 2,
    });
  }

  return formatCompanyField(raw as string | null | undefined);
}

export function companySearchText(company: Company): string {
  return [
    company.id,
    company.project_name,
    company.account_name,
    company.industry,
    company.name,
    company.description,
    company.investors,
    company.website,
    company.stage_name,
    company.type,
    company.lead_source,
    company.status,
    company.opportunity_owner,
    company.opportunity_owner_role,
    company.opportunity_owner_email,
    company.linked_in_company_id,
    company.zoom_info_company_id,
  ]
    .filter((v) => v != null && v !== "")
    .join(" ")
    .toLowerCase();
}

export function matchesCompanySearch(company: Company, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return companySearchText(company).includes(q);
}

export function matchesCompanyFilters(
  company: Company,
  filters: CompanyFiltersState,
): boolean {
  if (filters.industry && (company.industry ?? "") !== filters.industry) return false;
  if (filters.stage_name && (company.stage_name ?? "") !== filters.stage_name) return false;
  if (filters.lead_source && (company.lead_source ?? "") !== filters.lead_source) return false;
  if (filters.status && (company.status ?? "") !== filters.status) return false;
  return true;
}

export function uniqueFilterValues(
  companies: Company[],
  field: keyof Pick<Company, "industry" | "stage_name" | "lead_source" | "status">,
): string[] {
  const values = new Set<string>();
  for (const company of companies) {
    const value = company[field];
    if (value) values.add(value);
  }
  return [...values].sort((a, b) => a.localeCompare(b));
}

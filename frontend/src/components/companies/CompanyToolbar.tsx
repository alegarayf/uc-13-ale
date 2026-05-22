import type { Company, CompanyFiltersState } from "../../types/company.js";
import { uniqueFilterValues } from "../../utils/companyDisplay.js";

export interface CompanyToolbarProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  filters: CompanyFiltersState;
  onFilterChange: (field: keyof CompanyFiltersState, value: string) => void;
  companies: Company[];
}

const FILTER_FIELDS: {
  key: keyof CompanyFiltersState;
  label: string;
  companyField: keyof Pick<Company, "industry" | "stage_name" | "lead_source" | "status">;
}[] = [
  { key: "industry", label: "Industry", companyField: "industry" },
  { key: "stage_name", label: "Stage name", companyField: "stage_name" },
  { key: "lead_source", label: "Lead source", companyField: "lead_source" },
  { key: "status", label: "Status", companyField: "status" },
];

export function CompanyToolbar({
  searchQuery,
  onSearchChange,
  filters,
  onFilterChange,
  companies,
}: CompanyToolbarProps) {
  return (
    <div className="company-toolbar">
      <div className="company-toolbar__search">
        <label className="company-toolbar__search-label" htmlFor="company-search">
          Search companies
        </label>
        <input
          id="company-search"
          type="search"
          className="form-field__input company-toolbar__search-input"
          placeholder="Search by name, industry, stage…"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <div className="company-toolbar__filters" role="group" aria-label="Filter companies">
        {FILTER_FIELDS.map(({ key, label, companyField }) => {
          const options = uniqueFilterValues(companies, companyField);
          return (
            <div key={key} className="company-toolbar__filter">
              <label className="company-toolbar__filter-label" htmlFor={`filter-${key}`}>
                {label}
              </label>
              <select
                id={`filter-${key}`}
                className="form-field__input company-toolbar__filter-select"
                value={filters[key]}
                onChange={(e) => onFilterChange(key, e.target.value)}
              >
                <option value="">All</option>
                {options.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
}

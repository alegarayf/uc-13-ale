import { useEffect, useMemo, useState } from "react";
import { fetchApiConfig } from "../api/config.js";
import { fetchCompanies, fetchCompany } from "../api/companies.js";
import { CompanyDetailView } from "../components/companies/CompanyDetailView.js";
import { CompanyToolbar } from "../components/companies/CompanyToolbar.js";
import type { Company } from "../types/company.js";
import { EMPTY_COMPANY_FILTERS, type CompanyFiltersState } from "../types/company.js";
import {
  formatCompanyField,
  matchesCompanyFilters,
  matchesCompanySearch,
} from "../utils/companyDisplay.js";

type GardenView = "list" | "detail";

export function MyGarden() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [dataStore, setDataStore] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState<CompanyFiltersState>(EMPTY_COMPANY_FILTERS);
  const [view, setView] = useState<GardenView>("list");
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [config, data] = await Promise.all([fetchApiConfig(), fetchCompanies()]);
        if (!cancelled) {
          setDataStore(config.dataStore);
          setCompanies(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load companies";
          setError(
            message === "Failed to fetch"
              ? "Could not reach the API. Start it with npm run dev (or npm run dev:api) and confirm VITE_API_BASE_URL in .env."
              : message,
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredCompanies = useMemo(
    () =>
      companies.filter(
        (c) => matchesCompanySearch(c, searchQuery) && matchesCompanyFilters(c, filters),
      ),
    [companies, searchQuery, filters],
  );

  function handleFilterChange(field: keyof CompanyFiltersState, value: string) {
    setFilters((prev) => ({ ...prev, [field]: value }));
  }

  function openDetail(company: Company) {
    setSelectedCompany(company);
    setView("detail");
    setDetailError(null);
    setDetailLoading(true);

    void fetchCompany(company.id)
      .then((full) => {
        setSelectedCompany(full);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Failed to load company details";
        setDetailError(message);
      })
      .finally(() => {
        setDetailLoading(false);
      });
  }

  function closeDetail() {
    setView("list");
    setSelectedCompany(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  const showingDetail = view === "detail" && selectedCompany != null;

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">My Garden</h1>
        <p className="page__subtitle">
          Opportunities you own, sourced from Salesforce silver data.
        </p>
      </header>

      <section className="content-card" aria-labelledby="my-garden-heading">
        {showingDetail ? (
          <div className="content-card__toolbar">
            <h2 id="my-garden-heading" className="content-card__title content-card__title--inline">
              Company details
            </h2>
            <button type="button" className="btn btn--secondary" onClick={closeDetail}>
              ← Back to companies
            </button>
          </div>
        ) : (
          <h2 id="my-garden-heading" className="content-card__title">
            Your companies
          </h2>
        )}

        {loading && view === "list" && (
          <p className="content-card__note" role="status">
            Loading companies…
          </p>
        )}

        {error && view === "list" && (
          <p className="content-card__error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && showingDetail && selectedCompany && (
          <>
            <hr className="company-detail-view__rule" />
            <CompanyDetailView
              company={selectedCompany}
              loading={detailLoading}
              error={detailError}
            />
          </>
        )}

        {!loading && !error && view === "list" && (
          <>
            <p className="content-card__note">
              {filteredCompanies.length} shown · {companies.length} total
              {dataStore ? ` (data store: ${dataStore})` : ""}
            </p>

            {companies.length > 0 && (
              <CompanyToolbar
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                filters={filters}
                onFilterChange={handleFilterChange}
                companies={companies}
              />
            )}

            {filteredCompanies.length > 0 && (
              <div className="companies-table-wrap">
                <table className="companies-table">
                  <thead>
                    <tr>
                      <th scope="col">Project</th>
                      <th scope="col">Account</th>
                      <th scope="col">Industry</th>
                      <th scope="col">Website</th>
                      <th scope="col">Stage</th>
                      <th scope="col">Lead source</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCompanies.map((company) => (
                      <tr
                        key={company.id}
                        className="companies-table__row"
                        onClick={() => openDetail(company)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            openDetail(company);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-label={`View details for ${company.project_name}`}
                      >
                        <td>
                          <span className="companies-table__name">{company.project_name}</span>
                          <span className="companies-table__id">{company.id}</span>
                        </td>
                        <td>{company.account_name}</td>
                        <td>{formatCompanyField(company.industry)}</td>
                        <td>{formatCompanyField(company.website)}</td>
                        <td>{formatCompanyField(company.stage_name)}</td>
                        <td>{formatCompanyField(company.lead_source)}</td>
                        <td>
                          <span className="companies-table__status">
                            {formatCompanyField(company.status)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {companies.length > 0 && filteredCompanies.length === 0 && (
              <p className="content-card__note">
                No companies match your search or filters. Try clearing filters or broadening your
                search.
              </p>
            )}

            {companies.length === 0 && (
              <p className="content-card__note">
                No companies returned from the API
                {dataStore ? ` (data store: ${dataStore})` : ""}.{" "}
                {dataStore === "memory"
                  ? "The in-memory store should include 15 seed companies for your account — try restarting the API."
                  : dataStore === "databricks"
                    ? "Confirm salesforce_silver.opportunity_silver is populated and OpportunityOwnerEmail matches your user."
                    : "Check the opportunity silver view and owner email filter."}
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

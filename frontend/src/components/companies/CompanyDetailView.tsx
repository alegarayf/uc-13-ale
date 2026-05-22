import type { Company } from "../../types/company.js";
import {
  formatCompanyDetailValue,
  formatCompanyField,
} from "../../utils/companyDisplay.js";
import { COMPANY_DETAIL_FIELDS, type CompanyDetailField } from "../../utils/companyDetailFields.js";

export interface CompanyDetailViewProps {
  company: Company;
  loading?: boolean;
  error?: string | null;
  onBack: () => void;
}

function DetailValue({ company, field }: { company: Company; field: CompanyDetailField }) {
  const raw = company[field.key];

  if (field.format === "url") {
    const href = typeof raw === "string" ? raw.trim() : "";
    const text = formatCompanyField(raw as string | null);
    if (!href) return <>{text}</>;
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {href}
      </a>
    );
  }

  if (field.format === "status") {
    return (
      <span className="company-detail__status">
        {formatCompanyDetailValue(company, field)}
      </span>
    );
  }

  if (field.format === "mono") {
    return <span className="company-detail__id">{formatCompanyDetailValue(company, field)}</span>;
  }

  if (field.format === "multiline") {
    const text = formatCompanyField(raw as string | null);
    if (text === "—") return <>{text}</>;
    return <p className="company-detail__multiline">{text}</p>;
  }

  return <>{formatCompanyDetailValue(company, field)}</>;
}

export function CompanyDetailView({ company, loading, error, onBack }: CompanyDetailViewProps) {
  return (
    <div className="company-detail-view">
      <div className="company-detail-view__toolbar">
        <button type="button" className="btn btn--secondary" onClick={onBack}>
          ← Back to companies
        </button>
      </div>

      <header className="company-detail-view__header">
        <h2 className="company-detail-view__title">{company.project_name}</h2>
        <p className="company-detail-view__subtitle">
          {company.account_name}
          {company.status ? ` · ${company.status}` : ""}
        </p>
      </header>

      {error && (
        <p className="content-card__error" role="alert">
          {error}
        </p>
      )}

      {loading && (
        <p className="content-card__note" role="status">
          Refreshing record…
        </p>
      )}

      <dl className="company-detail-view__list" aria-busy={loading}>
        {COMPANY_DETAIL_FIELDS.map((field) => (
          <div key={field.key} className="company-detail-view__row">
            <dt>{field.label}</dt>
            <dd>
              <DetailValue company={company} field={field} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

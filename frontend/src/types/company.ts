export interface Company {
  id: string;
  project_name: string;
  account_name: string;
  industry: string | null;
  annual_revenue: number | null;
  employee_head_count: number | null;
  year_founded: number | null;
  ebitda: number | null;
  ebitda_margin: number | null;
  days_since_last_activity: number | null;
  website: string | null;
  source_scrub_url: string | null;
  linked_in_company_id: string | null;
  zoom_info_company_id: string | null;
  growth_rate_12_months: number | null;
  growth_rate_9_months: number | null;
  growth_rate_6_months: number | null;
  investors: string | null;
  name: string | null;
  description: string | null;
  stage_name: string | null;
  type: string | null;
  lead_source: string | null;
  opportunity_owner: string | null;
  opportunity_owner_role: string | null;
  opportunity_owner_email: string | null;
  status: string | null;
}

export interface ApiListResponse<T> {
  data: T[];
}

export interface ApiItemResponse<T> {
  data: T;
}

export interface ApiErrorBody {
  error: {
    message: string;
    code?: string;
  };
}

export interface CompanyFiltersState {
  industry: string;
  stage_name: string;
  lead_source: string;
  status: string;
}

export const EMPTY_COMPANY_FILTERS: CompanyFiltersState = {
  industry: "",
  stage_name: "",
  lead_source: "",
  status: "",
};

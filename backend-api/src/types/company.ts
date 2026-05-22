/** Opportunity / company record from salesforce_silver.opportunity_silver. */
export interface CompanyFields {
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

export class Company implements CompanyFields {
  readonly id: string;
  readonly project_name: string;
  readonly account_name: string;
  readonly industry: string | null;
  readonly annual_revenue: number | null;
  readonly employee_head_count: number | null;
  readonly year_founded: number | null;
  readonly ebitda: number | null;
  readonly ebitda_margin: number | null;
  readonly days_since_last_activity: number | null;
  readonly website: string | null;
  readonly source_scrub_url: string | null;
  readonly linked_in_company_id: string | null;
  readonly zoom_info_company_id: string | null;
  readonly growth_rate_12_months: number | null;
  readonly growth_rate_9_months: number | null;
  readonly growth_rate_6_months: number | null;
  readonly investors: string | null;
  readonly name: string | null;
  readonly description: string | null;
  readonly stage_name: string | null;
  readonly type: string | null;
  readonly lead_source: string | null;
  readonly opportunity_owner: string | null;
  readonly opportunity_owner_role: string | null;
  readonly opportunity_owner_email: string | null;
  readonly status: string | null;

  constructor(fields: CompanyFields) {
    this.id = fields.id;
    this.project_name = fields.project_name;
    this.account_name = fields.account_name;
    this.industry = fields.industry;
    this.annual_revenue = fields.annual_revenue;
    this.employee_head_count = fields.employee_head_count;
    this.year_founded = fields.year_founded;
    this.ebitda = fields.ebitda;
    this.ebitda_margin = fields.ebitda_margin;
    this.days_since_last_activity = fields.days_since_last_activity;
    this.website = fields.website;
    this.source_scrub_url = fields.source_scrub_url;
    this.linked_in_company_id = fields.linked_in_company_id;
    this.zoom_info_company_id = fields.zoom_info_company_id;
    this.growth_rate_12_months = fields.growth_rate_12_months;
    this.growth_rate_9_months = fields.growth_rate_9_months;
    this.growth_rate_6_months = fields.growth_rate_6_months;
    this.investors = fields.investors;
    this.name = fields.name;
    this.description = fields.description;
    this.stage_name = fields.stage_name;
    this.type = fields.type;
    this.lead_source = fields.lead_source;
    this.opportunity_owner = fields.opportunity_owner;
    this.opportunity_owner_role = fields.opportunity_owner_role;
    this.opportunity_owner_email = fields.opportunity_owner_email;
    this.status = fields.status;
  }
}

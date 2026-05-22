# Companies API

Read-only access to Salesforce opportunity records from the `salesforce_silver.opportunity_silver` materialized view. See [architecture.md](../architecture.md) for layering.

**Base URL (local):** `http://localhost:${BACKEND_API_PORT}` (default `3001`)

**Prefix:** `/api/companies`

## Authorization model (interim)

Until auth is wired, the API scopes results to a fixed owner email (`mcrysler@nimblegravity.com` in `CompaniesService`). Only opportunities whose `OpportunityOwnerEmail` matches that value are returned on list; detail requests return `404` for records owned by someone else or with a missing owner email.

## Resource model

`Company` is a plain JSON object (not `BaseApiModel` — Salesforce string ids, no audit timestamps).

| Field | Type | Salesforce column |
|-------|------|-------------------|
| `id` | string | `Id` |
| `project_name` | string | `ProjectName` |
| `account_name` | string | `AccountName` |
| `industry` | string \| null | `Industry` |
| `annual_revenue` | number \| null | `AnnualRevenue` (decimal) |
| `employee_head_count` | number \| null | `EmployeeHeadCount` (int) |
| `year_founded` | number \| null | `YearFounded` (double) |
| `ebitda` | number \| null | `EBITDA` (decimal) |
| `ebitda_margin` | number \| null | `EBITDAMargin` (double) |
| `days_since_last_activity` | number \| null | `DaysSinceLastActivity` (double) |
| `website` | string \| null | `Website` |
| `source_scrub_url` | string \| null | `SourceScrubUrl` |
| `linked_in_company_id` | string \| null | `LinkedInCompanyId` |
| `zoom_info_company_id` | string \| null | `ZoomInfoCompanyId` |
| `growth_rate_12_months` | number \| null | `GrowthRate12Months` (double) |
| `growth_rate_9_months` | number \| null | `GrowthRate9Months` (double) |
| `growth_rate_6_months` | number \| null | `GrowthRate6Months` (double) |
| `investors` | string \| null | `Investors` |
| `name` | string \| null | `Name` |
| `description` | string \| null | `Description` |
| `stage_name` | string \| null | `StageName` |
| `type` | string \| null | `Type` |
| `lead_source` | string \| null | `LeadSource` |
| `opportunity_owner` | string \| null | `OpportunityOwner` |
| `opportunity_owner_role` | string \| null | `OpportunityOwnerRole` |
| `opportunity_owner_email` | string \| null | `OpportunityOwnerEmail` (scoping) |
| `status` | string \| null | `Status` |

## Endpoints

### List companies (current user)

```http
GET /api/companies
```

Returns all opportunities owned by the configured default user email.

**200 OK**

```json
{
  "data": [
    {
      "id": "opp-001",
      "project_name": "Northwind Expansion",
      "account_name": "Northwind Traders",
      "industry": "Manufacturing",
      "website": "https://northwind.example.com",
      "stage_name": "Qualification",
      "lead_source": "Partner Referral",
      "status": "Open",
      "opportunity_owner_email": "mcrysler@nimblegravity.com"
    }
  ]
}
```

---

### Get company by id

```http
GET /api/companies/:id
```

`:id` — non-empty string (Salesforce id or seed id in memory mode).

| Status | When |
|--------|------|
| 200 | Found and owned by the default user |
| 400 | Blank or missing id |
| 404 | Not found, wrong owner, or missing `opportunity_owner_email` |

---

## Error format

Same as [rules API](./rules.md#error-format).

## Caching

When `API_CACHE_TTL_SECONDS` > 0:

- `GET` list and detail may be served from an in-process TTL cache (`cachingCompaniesRepository`).
- Successful `GET` responses include `Cache-Control: private, max-age=N`.
- This API is read-only; no write invalidation paths exist yet.

## Databricks setup

1. Ensure the materialized view `salesforce_silver.opportunity_silver` exists and is readable from your SQL warehouse.
2. Set `DATA_STORE=databricks` and `DATABRICKS_*` in `.env` (catalog/schema env vars apply to `garden.rules`; the opportunity view uses a fixed three-part name — see `opportunitySilverTableRef()` in `src/db/tableRef.ts`).
3. Rows must include `OpportunityOwnerEmail` (and the columns listed in `OPPORTUNITY_SELECT_COLUMNS` in `companyRowMapper.ts`).

With `DATA_STORE=memory`, five seed companies are returned for the default owner; a sixth seed row (`opp-999`) exists for another owner and is excluded from list/detail for the default user.

## Examples (curl)

```bash
# List
curl -s http://localhost:3001/api/companies

# Detail
curl -s http://localhost:3001/api/companies/opp-001
```

## Changelog

| Date | Change |
|------|--------|
| 2026-05-22 | Initial read-only companies API; opportunity silver view; owner email scoping |

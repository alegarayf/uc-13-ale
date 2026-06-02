# Rules API (`/api/rules`)

CRUD for `garden.rules`. Rules are either **form**-authored (simple name/description) or **ai**-authored (natural language + Genie JSON definition + Python).

## Entity fields

| Field | Type | Required on create | Notes |
|-------|------|-------------------|--------|
| `id` | integer | — | Server-generated |
| `name` | string | yes | |
| `description` | string \| null | no | |
| `status` | string | no (default `active`) | `active` \| `inactive` |
| `rule_source` | string | no (default `form`) | `form` \| `ai` |
| `nl_prompt` | string \| null | no | Original NL prompt (AI rules) |
| `nl_summary` | string \| null | no | Genie prose summary (AI rules) |
| `rule_definition` | string \| null | no | JSON string (conditions, actions, `python_function`, etc.) |
| `python_source` | string \| null | no | Extracted from `rule_definition` on write if omitted |
| `python_entrypoint` | string \| null | no | Extracted from `rule_definition` on write if omitted |
| `created_at` | string (ISO) | — | Server-set |
| `updated_at` | string (ISO) | — | Server-set |
| `last_updated_by` | string \| null | no | |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/rules` | List all rules |
| GET | `/api/rules/:id` | Get one rule |
| POST | `/api/rules` | Create |
| PUT | `/api/rules/:id` | Full replace |
| PATCH | `/api/rules/:id` | Partial update |
| DELETE | `/api/rules/:id` | Delete |

## Example: create AI rule

```json
POST /api/rules
{
  "name": "employee_headcount_investment_range",
  "description": "Headcount between 50 and 350",
  "status": "active",
  "rule_source": "ai",
  "nl_prompt": "Companies should have 50–350 employees…",
  "nl_summary": "Opportunities are eligible when employee_head_count is 50–350 inclusive.",
  "rule_definition": "{\"name\":\"employee_headcount_investment_range\",\"conditions\":[...],\"python_function\":{...}}",
  "last_updated_by": "Matt Crysler"
}
```

If `python_source` / `python_entrypoint` are omitted, the API extracts them from `rule_definition.python_function` when present.

## Natural language authoring

The UI calls `backend-ai` (`POST /api/ai/rules/interpret`, `POST /api/ai/rules/sessions/:id/deny`) for Genie interpretation, then persists the confirmed rule via `POST` or `PUT` on this API. Config files are not used.

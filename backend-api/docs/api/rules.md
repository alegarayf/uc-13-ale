# Rules API

CRUD for garden evaluation rules stored in `garden.rules` (Unity Catalog). See [architecture.md](../architecture.md) for layering and [create_rules_table.sql](../../../databricks/jobs/sql/create_rules_table.sql) for DDL.

**Base URL (local):** `http://localhost:${BACKEND_API_PORT}` (default `3001`)

**Prefix:** `/api/rules`

## Resource model

`Rule` extends the shared audit fields from `BaseApiModel`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | read-only | Surrogate key (identity in Databricks) |
| `name` | string | yes | Rule display name |
| `description` | string \| null | no | Longer explanation |
| `comparison` | string \| null | no | One of `=`, `<`, `>`, `<=`, `>=` (matches DB check constraint) |
| `minimum` | integer \| null | no | Lower bound for comparisons |
| `maximum` | integer \| null | no | Upper bound for comparisons |
| `uom` | string \| null | no | Unit of measure |
| `status` | string | no | `active` or `inactive` (defaults to `active` on create) |
| `created_at` | string (ISO-8601) | read-only | Set on create |
| `updated_at` | string (ISO-8601) | read-only | Set on create; refreshed on update |
| `last_updated_by` | string \| null | no | Audit label (user/service id) |

## Endpoints

### List rules

```http
GET /api/rules
```

**200 OK**

```json
{
  "data": [
    {
      "id": 1,
      "name": "Revenue threshold",
      "description": "Minimum annual revenue for portfolio consideration.",
      "comparison": ">=",
      "minimum": 10000000,
      "maximum": null,
      "uom": "USD",
      "status": "active",
      "created_at": "2026-01-01T00:00:00.000Z",
      "updated_at": "2026-01-01T00:00:00.000Z",
      "last_updated_by": "seed"
    }
  ]
}
```

---

### Get rule by id

```http
GET /api/rules/:id
```

`:id` — positive integer.

| Status | When |
|--------|------|
| 200 | Found |
| 400 | Invalid id |
| 404 | Not found |

---

### Create rule

```http
POST /api/rules
Content-Type: application/json
```

**Body** (identity and timestamps are server-owned):

```json
{
  "name": "Headcount",
  "description": "Team size",
  "comparison": ">=",
  "minimum": 5,
  "maximum": null,
  "uom": "employees",
  "status": "active",
  "last_updated_by": "jane.doe"
}
```

| Status | When |
|--------|------|
| 201 | Created |
| 400 | Validation error (e.g. missing `name`, invalid `comparison` or `status`) |

---

### Replace rule (full update)

```http
PUT /api/rules/:id
Content-Type: application/json
```

All business fields should be sent. `comparison` may be `null`. `status` must be `active` or `inactive`. `created_at` is unchanged; `updated_at` is refreshed server-side.

```json
{
  "name": "Headcount (revised)",
  "description": null,
  "comparison": ">=",
  "minimum": 10,
  "maximum": 100,
  "uom": "employees",
  "status": "active",
  "last_updated_by": "jane.doe"
}
```

| Status | When |
|--------|------|
| 200 | Updated |
| 400 | Validation error |
| 404 | Not found |

---

### Partial update

```http
PATCH /api/rules/:id
Content-Type: application/json
```

At least one mutable field required.

```json
{
  "minimum": 8,
  "last_updated_by": "jane.doe"
}
```

| Status | When |
|--------|------|
| 200 | Updated |
| 400 | Empty body or validation error |
| 404 | Not found |

---

### Delete rule

```http
DELETE /api/rules/:id
```

| Status | When |
|--------|------|
| 204 | Deleted (no body) |
| 404 | Not found |

## Error format

```json
{
  "error": {
    "message": "Rule not found: 999",
    "code": "NOT_FOUND"
  }
}
```

| Code | HTTP | Meaning |
|------|------|---------|
| `VALIDATION_ERROR` | 400 | Bad input |
| `NOT_FOUND` | 404 | Unknown id |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Caching

When `API_CACHE_TTL_SECONDS` > 0 (default `60`):

- `GET` list and detail responses may be served from an in-process TTL cache.
- Successful `GET` responses include `Cache-Control: private, max-age=N`.
- `POST`, `PUT`, `PATCH`, and `DELETE` invalidate cached reads.

See [architecture.md](../architecture.md#caching).

## Databricks setup

1. Run `databricks/jobs/sql/create_rules_table.sql` in your warehouse (adjust catalog/schema).
2. Optionally run `databricks/jobs/sql/seed_rules.sql` for sample rows.
3. Set `DATA_STORE=databricks` and `DATABRICKS_*` in `.env`.

With `DATA_STORE=memory`, three seed rules are available without a warehouse.

## Examples (curl)

```bash
# List
curl -s http://localhost:3001/api/rules

# Create
curl -s -X POST http://localhost:3001/api/rules \
  -H 'Content-Type: application/json' \
  -d '{"name":"Margin","comparison":">=","minimum":20,"uom":"percent","status":"active","last_updated_by":"dev"}'

# Full replace (edit)
curl -s -X PUT http://localhost:3001/api/rules/1 \
  -H 'Content-Type: application/json' \
  -d '{"name":"Margin (revised)","description":null,"comparison":">=","minimum":25,"maximum":null,"uom":"percent","status":"active","last_updated_by":"dev"}'

# Partial update
curl -s -X PATCH http://localhost:3001/api/rules/1 \
  -H 'Content-Type: application/json' \
  -d '{"minimum":15000000,"status":"inactive"}'

# Delete
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://localhost:3001/api/rules/4
```

## Changelog

| Date | Change |
|------|--------|
| 2026-05-20 | Initial rules CRUD; schema with comparison/min/max/uom and identity `id` |
| 2026-05-20 | Added `status` (`active` / `inactive`) |
| 2026-05-20 | TTL read cache + `Cache-Control` on GET; cache invalidation on writes |
| 2026-05-20 | Frontend Garden rules UI: list, add, edit, delete |

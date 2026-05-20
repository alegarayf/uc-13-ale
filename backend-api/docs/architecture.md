# Backend API architecture

The `backend-api` package is a Node.js + Express REST service that fronts Databricks (Unity Catalog) for Rallyday. It is designed so the UI and other clients talk only to HTTP JSON APIs, while database access stays centralized and swappable for local development.

## Layered design

```
HTTP (Express routes)
        ↓
Services (validation, orchestration)
        ↓
Repositories (SQL / in-memory persistence)
        ↓
DB client (Databricks SQL driver)  OR  memory store
```

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **Routes** | `src/routes/` | Map HTTP verbs and paths to service calls; parse path params; return JSON envelopes. |
| **Services** | `src/services/` | Business rules, input validation, error translation. No SQL here. |
| **Repositories** | `src/repositories/` | CRUD for each table/entity. One repository per aggregate. |
| **DB** | `src/db/` | Databricks connection pooling and parameterized queries. |
| **Types** | `src/types/` | API models (classes) shared by layers. |

### Why this split

- **Multiple APIs will share the database** — repositories and `DatabricksClient` are reused instead of embedding SQL in route handlers.
- **Testability** — services accept repository interfaces; HTTP tests inject an in-memory repository via `createApp()` (`src/app.ts`).
- **Environment switching** — `DATA_STORE=memory|databricks` selects implementation without changing routes or services.

## Base API model

All persisted entities extend `BaseApiModel` (`src/types/baseApiModel.ts`):

| Field | Type (JSON) | Notes |
|-------|-------------|--------|
| `id` | number | Databricks: `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `created_at` | string (ISO-8601) | Set on insert; never changed by updates |
| `updated_at` | string (ISO-8601) | Refreshed on insert and update |
| `last_updated_by` | string \| null | Caller-provided audit hint until auth is wired |

Domain models (e.g. `Rule`) subclass `BaseApiModel` and add entity-specific fields.

`Rule` adds: `name`, `description`, `comparison`, `minimum`, `maximum`, `uom`, `status` (`active` | `inactive`).

## Data stores

| Mode | Env | Behavior |
|------|-----|----------|
| `memory` | `DATA_STORE=memory` (default) | In-memory repositories with seed data; no warehouse required. |
| `databricks` | `DATA_STORE=databricks` | `@databricks/sql` against `DATABRICKS_CATALOG.DATABRICKS_SCHEMA.<table>`. |

Configuration is loaded from the repo-root `.env` (see `src/loadEnv.ts`). Health check: `GET /health` runs a store-specific ping (`SELECT 1` for Databricks).

## Caching

Read-heavy API paths use a **TTL cache** in the repository layer to avoid repeated Databricks SQL for identical requests.

| Mechanism | Location | Behavior |
|-----------|----------|----------|
| **Server TTL cache** | `src/repositories/cachingRulesRepository.ts` | Wraps `RulesRepository` reads (`findAll`, `findById`). Writes invalidate list + affected ids. |
| **HTTP `Cache-Control`** | `src/middleware/cacheControl.ts` | Successful GET responses include `private, max-age=N` (same window as TTL). |

Configure with `API_CACHE_TTL_SECONDS` in `.env` (default `60`). Set to `0` to disable both layers.

`GET /api/config` reports `cache.enabled` and `cache.ttlSeconds`.

The cache is **in-process** (single API instance). For horizontal scale, replace with Redis or disable short TTL until shared cache exists.

Future repositories should use the same decorator pattern: cache reads, invalidate on mutations.

## Databricks table naming

Runtime SQL uses a fully qualified name:

```text
{catalog}.{schema}.rules
```

DDL in `databricks/jobs/sql/create_rules_table.sql` may use schema-local names (`garden.rules`); align catalog/schema with `DATABRICKS_CATALOG` and `DATABRICKS_SCHEMA` in `.env`.

## REST conventions

- JSON request and response bodies.
- Success collections: `{ "data": [ ... ] }`.
- Success single resource: `{ "data": { ... } }`.
- Errors: `{ "error": { "message": "...", "code": "VALIDATION_ERROR" | "NOT_FOUND" | ... } }`.
- Numeric path IDs (e.g. `/api/rules/42`).
- `POST` → `201 Created`; `DELETE` → `204 No Content`.

## Application bootstrap

- `src/app.ts` — `createApp()` builds Express without listening (used in tests).
- `src/index.ts` — loads config, calls `createApp()`, listens on `BACKEND_API_PORT`.

## Frontend consumer

The React app (`frontend/`) calls this API via `VITE_API_BASE_URL`. The Garden rules page (`/garden-rules`) uses:

- `GET /api/rules` — table data
- `POST /api/rules` — add modal
- `PUT /api/rules/:id` — edit modal (full replace)
- `DELETE /api/rules/:id` — delete confirmation

See [frontend/docs/README.md](../../frontend/docs/README.md).

Writes invalidate the server-side rules cache so the UI sees fresh data on the next list fetch (the UI also updates local state immediately after create/edit/delete).

## Testing strategy

Tests live in `backend-api/tests/` and use **Vitest** + **Supertest**.

| Suite | What it covers |
|-------|----------------|
| `validation.test.ts` | Input normalization |
| `rulesService.test.ts` | Service logic with mocked repository |
| `rulesRepository.*.test.ts` | Memory and Databricks repositories |
| `rules.routes.test.ts` | Full HTTP stack with in-memory app (GET/POST/PUT/PATCH/DELETE) |
| `cachingRulesRepository.test.ts` | Cache hits and invalidation on create/update/delete |
| `cacheControl.test.ts`, `TtlCache.test.ts` | HTTP `Cache-Control` and TTL store |
| `ruleRowMapper.test.ts`, `tableRef.test.ts`, etc. | Supporting modules |

Run `npm run test:coverage -w backend-api` before merging API changes. Coverage thresholds are configured in `vitest.config.ts` (≥85% lines/functions/statements).

## Adding a new API

1. Add SQL DDL under `databricks/jobs/sql/` if needed.
2. Define a model extending `BaseApiModel` in `src/types/`.
3. Add `src/repositories/<entity>Repository.ts` (+ memory and Databricks factories).
4. Add `src/services/<entity>Service.ts` for validation and orchestration.
5. Add `src/routes/<entity>.ts` and register in `src/app.ts`.
6. Document under `docs/api/<entity>.md`.
7. Add unit tests mirroring the rules suites.

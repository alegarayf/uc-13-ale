# uc-13-ale

Monorepo for a multi-component application:

- **frontend** — React, TypeScript, Vite
- **backend-api** — Node.js, Express, TypeScript (REST for the UI; data layer pluggable)
- **backend-ai** — Python, FastAPI (AI / workflow APIs callable from the API or UI)
- **databricks** — Databricks-facing assets: **`jobs/`** (batch / sync scripts and tasks for **Databricks Jobs**) and **`agents/`** (Databricks Agents)

Deployments target **Databricks** (warehouses, Unity Catalog, Jobs) rather than Azure-specific PaaS. Use Databricks SQL / SDK in `backend-api` when `DATA_STORE=databricks`.

## Layout

```
uc-13-ale/
├── .env.example          # Copy to `.env` at repo root (see Environment)
├── package.json          # Workspaces + concurrent dev scripts
├── tsconfig.base.json
├── frontend/             # React UI (My Garden, Garden rules with AI)
├── backend-api/          # Express REST API + docs in backend-api/docs/
├── backend-ai/
└── databricks/
    ├── jobs/
    │   └── sql/          # Table DDL + seed data (e.g. garden.rules)
    └── agents/           # Databricks Agents definitions / code
```

## Prerequisites

- Node.js 20+
- Python 3.12+ (recommended for `backend-ai` and `databricks/jobs`)

## Quick start

```bash
cp .env.example .env
npm install
npm run install:all
npm run dev
```

- **Frontend**: `http://localhost:${FRONTEND_PORT}` (default `5173`)
- **Backend API**: `http://localhost:${BACKEND_API_PORT}` (default `3001`)
- **AI API**: `http://localhost:${BACKEND_AI_PORT}` (default `8000`), docs at `/docs`

Run a single service:

```bash
npm run dev:frontend
npm run dev:api
npm run dev:ai
```

## Environment

Create a **`.env` in the repository root** (gitignored). `npm run dev` loads it with `dotenv-cli` so all processes share the same ports and feature flags.

| Variable | Purpose |
|----------|---------|
| `DATA_STORE` | `memory` (default, in-process store for local dev) or `databricks` |
| `FRONTEND_PORT`, `BACKEND_API_PORT`, `BACKEND_AI_PORT` | Local ports |
| `VITE_*` | Frontend env (Vite `envDir` is the repo root) |
| `DATABRICKS_*` | Required when `DATA_STORE=databricks` (see `.env.example`) |
| `API_CACHE_TTL_SECONDS` | TTL for cached API reads — rules and companies (default `60`; `0` disables) |

`backend-api` also loads `backend-api/.env` if present (overrides root).

## Builds

```bash
npm run build
```

Produces `frontend/dist` and `backend-api/dist`.

## Tests & docs

```bash
npm run test                  # backend-api + frontend unit tests
npm run test:api              # backend only (Vitest + Supertest)
npm run test:api:coverage     # backend coverage report (backend-api/coverage/)
npm run test:frontend         # frontend unit tests (form helpers, formatting)
```

| Area | Documentation |
|------|----------------|
| Backend API | [`backend-api/docs/`](backend-api/docs/README.md) — architecture, [rules](backend-api/docs/api/rules.md) and [companies](backend-api/docs/api/companies.md) REST APIs, caching |
| Frontend | [`frontend/docs/`](frontend/docs/README.md) — My Garden and Garden rules UI |

**My Garden** (local): open `/my-garden` after `npm run dev`. With `DATA_STORE=memory`, fifteen seed opportunities (full field coverage) are returned for the configured owner email. With `DATA_STORE=databricks`, data comes from `salesforce_silver.opportunity_silver`.

**Garden rules** (local): open `/garden-rules` after `npm run dev`. Use `DATA_STORE=memory` for seeded sample rules, or `DATA_STORE=databricks` with SQL in `databricks/jobs/sql/`.

## Databricks

The **`databricks/jobs/`** tree holds code packaged or referenced by Databricks Jobs (Python scripts, notebooks, SQL files, or future Scala/JAR tasks). SQL under `databricks/jobs/sql/` includes `create_rules_table.sql` and optional `seed_rules.sql` for the rules API. Jobs do not run automatically with `npm run dev`; deploy and schedule them in Databricks.

The **`databricks/agents/`** tree is reserved for Databricks Agents (definitions, prompts, tools, or supporting code you deploy with Agent Framework / workspace assets).

## Notes

This repo mirrors common monorepo patterns from full-stack READMEs (concurrent dev, typed API, separate AI service) with **root-level configuration** for local data mode and ports.

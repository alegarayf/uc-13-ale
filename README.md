# Rallyday

Monorepo for a multi-component application:

- **frontend** — React, TypeScript, Vite
- **backend-api** — Node.js, Express, TypeScript (REST for the UI; data layer pluggable)
- **backend-ai** — Python, FastAPI (AI / workflow APIs callable from the API or UI)
- **databricks** — Databricks-facing assets: **`jobs/`** (batch / sync scripts and tasks for **Databricks Jobs**) and **`agents/`** (Databricks Agents)

Deployments target **Databricks** (warehouses, Unity Catalog, Jobs) rather than Azure-specific PaaS. Use Databricks SQL / SDK in `backend-api` when `DATA_STORE=databricks`.

## Layout

```
Rallyday/
├── .env.example          # Copy to `.env` at repo root (see Environment)
├── package.json          # Workspaces + concurrent dev scripts
├── tsconfig.base.json
├── frontend/
├── backend-api/
├── backend-ai/
└── databricks/
    ├── jobs/
    │   └── scripts/      # Example job entrypoints (notebooks/wheels can live alongside)
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

`backend-api` also loads `backend-api/.env` if present (overrides root).

## Builds

```bash
npm run build
```

Produces `frontend/dist` and `backend-api/dist`.

## Databricks

The **`databricks/jobs/`** tree holds code packaged or referenced by Databricks Jobs (Python scripts, notebooks, SQL files, or future Scala/JAR tasks). It does not run automatically with `npm run dev`; deploy and schedule those tasks in Databricks.

The **`databricks/agents/`** tree is reserved for Databricks Agents (definitions, prompts, tools, or supporting code you deploy with Agent Framework / workspace assets).

## Notes

This repo mirrors common monorepo patterns from full-stack READMEs (concurrent dev, typed API, separate AI service) with **root-level configuration** for local data mode and ports.

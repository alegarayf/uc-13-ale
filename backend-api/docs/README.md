# Backend API documentation

Documentation for the Rallyday `backend-api` service.

| Document | Description |
|----------|-------------|
| [architecture.md](./architecture.md) | Layering, data stores, caching, and cross-cutting decisions |
| [api/rules.md](./api/rules.md) | Rules REST API reference |
| [api/companies.md](./api/companies.md) | Companies (My Garden) read-only REST API |

Related SQL assets: `databricks/jobs/sql/create_rules_table.sql`, `databricks/jobs/sql/seed_rules.sql`.

## Running tests

From the repository root:

```bash
npm run test:api
npm run test:api:coverage   # HTML report: backend-api/coverage/index.html
```

From `backend-api/`:

```bash
npm test
npm run test:coverage
```

### Test suites (`backend-api/tests/`)

| Suite | Coverage |
|-------|----------|
| `rules.routes.test.ts` | HTTP CRUD, validation, status field |
| `companies.routes.test.ts` | Companies HTTP reads, owner scoping, validation |
| `rulesService.test.ts` | Service orchestration |
| `companiesService.test.ts` | Owner scoping and not-found paths |
| `rulesRepository.memory.test.ts` | In-memory persistence |
| `companiesRepository.memory.test.ts` | In-memory opportunity seed data |
| `rulesRepository.databricks.test.ts` | Databricks SQL (mocked client) |
| `companiesRepository.databricks.test.ts` | Opportunity silver view queries (mocked) |
| `cachingRulesRepository.test.ts` | TTL cache + invalidation on writes |
| `cachingCompaniesRepository.test.ts` | TTL cache for company reads |
| `companyRowMapper.test.ts` | Row → `Company` mapping |
| `createCompaniesRepository.test.ts` | Repository factory + cache wiring |
| `validation.test.ts` | Comparison + status normalization |
| `ruleRowMapper.test.ts` | Row → `Rule` mapping |
| `cacheControl.test.ts`, `TtlCache.test.ts` | HTTP and in-process cache |
| `app.test.ts`, `createStore.test.ts`, `databricksClient.test.ts`, … | Bootstrap and infrastructure |

Coverage thresholds are enforced in `vitest.config.ts` (≥85% lines/functions/statements).

# Frontend documentation

React + Vite UI for Rallyday. Environment variables are loaded from the **repository root** (see `frontend/vite.config.ts` `envDir`).

## My Garden (`/my-garden`)

Read-only list of Salesforce opportunities owned by the current user (interim: fixed owner email on the API).

| Feature | API | UI |
|---------|-----|-----|
| List | `GET /api/companies` | Table on `MyGarden.tsx` |
| Detail | `GET /api/companies/:id` | `CompanyDetailView` (replaces list in content pane; row click) |

Search and filters (industry, stage, lead source, status) are client-side in `companyDisplay.ts`.

### Key modules

```
frontend/src/
├── api/companies.ts
├── components/companies/
│   ├── CompanyToolbar.tsx
│   └── CompanyDetailView.tsx
├── pages/MyGarden.tsx
├── types/company.ts
└── utils/companyDisplay.ts
```

See [backend companies API](../../backend-api/docs/api/companies.md).

---

## Garden rules (`/garden-rules`)

The Garden rules page loads data from the backend API and supports full CRUD.

| Feature | API | UI component |
|---------|-----|----------------|
| List | `GET /api/rules` | Table on `GardenRules.tsx` |
| Create | `POST /api/rules` | `RuleFormModal` (add mode) |
| Edit | `PUT /api/rules/:id` | `RuleFormModal` (edit mode) |
| Delete | `DELETE /api/rules/:id` | `DeleteRuleDialog` |

### Configuration

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend API origin (default `http://localhost:3001`) |

### Key modules

```
frontend/src/
├── api/
│   ├── client.ts      # fetch helpers (GET, POST, PUT, DELETE)
│   ├── config.ts      # GET /api/config
│   └── rules.ts       # rules CRUD client
├── components/rules/
│   ├── RuleFormModal.tsx
│   ├── RuleFormFields.tsx
│   ├── DeleteRuleDialog.tsx
│   └── ruleForm.ts    # form state ↔ API payloads
├── pages/GardenRules.tsx
├── types/rule.ts      # mirrors backend Rule model
└── utils/formatRule.ts
```

Modals use the native `<dialog>` element (`showModal()`) so the page behind does not remount or flicker.

### Tests

```bash
npm run test -w frontend
```

Covers `formatRule` and `companyDisplay` helpers, plus `ruleForm` validation/mapping logic.

See also: [backend rules API](../../backend-api/docs/api/rules.md).

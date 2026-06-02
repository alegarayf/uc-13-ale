# `garden.rules` schema (current)

| Column | Type | Notes |
|--------|------|--------|
| `id` | BIGINT | Identity primary key |
| `name` | STRING | Display / machine name |
| `description` | STRING | Optional short description |
| `status` | STRING | `active` \| `inactive` |
| `rule_source` | STRING | `form` \| `ai` |
| `nl_prompt` | STRING | Natural-language prompt (AI rules) |
| `nl_summary` | STRING | Genie prose summary (AI rules) |
| `rule_definition` | STRING | JSON rule definition (conditions, actions, python_function, etc.) |
| `python_source` | STRING | Executable Python body (extracted from `rule_definition` when omitted on write) |
| `python_entrypoint` | STRING | Python function name |
| `created_at` | TIMESTAMP | Server-set on insert |
| `updated_at` | TIMESTAMP | Server-set on insert/update |
| `last_updated_by` | STRING | Audit |

AI rules are authored via Genie (`backend-ai`) and persisted through `POST /api/rules` with `rule_source: "ai"`. JSON config files under `rules-config/` are no longer used.

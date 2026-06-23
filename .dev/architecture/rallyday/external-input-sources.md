Section:      external-input-sources
Version:      1.0.0
Last updated: 2026-06-20

```
Source:               SharePoint data room folders (per company)
Format:               PDF, Excel (.xlsx), Word, CSV
Parser:               download_upload.py (raw bytes only); ingestion_parser.py (ai_parse_document, PyMuPDF vision, openpyxl)
Trust level:          partially trusted — client-provided deal documents; treated as authoritative for extraction but may be incomplete or OCR-noisy
Surfaces extracted:   Text chunks, HTML tables → markdown, vision-extracted chart/tabular pages, workstream tags, priority tiers, embeddings
Surfaces NOT extracted: Password-protected files, unsupported formats, files flagged should_parse=false by classifier
Volume:               Per-deal data room (tens to hundreds of files) [needs confirmation]
Sensitivity:          Confidential PE diligence material; mis-extraction affects investment decisions
Owner module:         databricks/jobs/scripts/ingestion_parser.py, document_classifier.py
```

```
Source:               User natural-language rule prompts (Garden Rules AI)
Format:               Plain text (HTTP JSON body, max 8000 chars)
Parser:               backend-ai Genie pipeline + response_parser.py
Trust level:          untrusted — user-authored; may attempt prompt injection toward Genie
Surfaces extracted:   summary, rule JSON, generated Python function
Surfaces NOT extracted: Arbitrary code execution (python_source stored, not executed by Garden app in-repo)
Volume:               Low — interactive UI usage
Sensitivity:          Rules affect opportunity evaluation logic when executed downstream
Owner module:         backend-ai/app/routes/rules_nl.py
```

```
Source:               Manual rule form input (Garden Rules form editor)
Format:               JSON via REST (CreateRuleInput)
Parser:               backend-api express.json + RulesService validation
Trust level:          partially trusted — authenticated users assumed [needs confirmation]
Surfaces extracted:   Rule entity fields, optional rule_definition JSON string
Surfaces NOT extracted: Server rejects empty name; status/source enum normalization
Volume:               Low — interactive
Sensitivity:          Same as NL rules when persisted
Owner module:         backend-api/src/services/rulesService.ts
```

```
Source:               Databricks Genie / Claude model responses
Format:               Plain text, markdown fences, embedded JSON
Parser:               response_parser.py, genie_message.py
Trust level:          untrusted — model output parsed with ast/json guards
Surfaces extracted:   Canonical { summary, rule } objects when parseable
Surfaces NOT extracted: Invalid JSON, invalid python_function.source (ParseError)
Volume:               1–2 Genie round-trips per NL rule interpret
Sensitivity:          Drives stored rule_definition and python_source
Owner module:         backend-ai/app/services/response_parser.py
```

```
Source:               Salesforce silver opportunity_silver view
Format:               Databricks SQL rows
Parser:               @databricks/sql row mapper (backend-api)
Trust level:          trusted — internal curated warehouse view
Surfaces extracted:   All Company API fields
Surfaces NOT extracted: Columns outside CompanyFields are not exposed
Volume:               Read-heavy list/detail for My Garden
Sensitivity:          CRM/deal pipeline data
Owner module:         backend-api/src/repositories/companiesRepository.ts
```

```
Source:               Client spec documents (Guidelines/)
Format:               PDF, TXT (reference only, not runtime-ingested by Garden app)
Parser:               Human / agent context (databricks/CLAUDE.md references)
Trust level:          trusted for product requirements
Surfaces extracted:   n/a at runtime
Surfaces NOT extracted: n/a
Volume:               Static
Sensitivity:          Product specification
Owner module:         databricks/Guidelines/
```

# Post-merge regression map — open backlog only

**Superseded:** 2026-08-26 — closed items live in `OPEN_ITEMS.md` § Closed. Full 2026-07 investigation log: `.dev/archive/post_merge_regressions.md`.

---

## Open / backlog

| Item | Status | Notes |
|------|--------|-------|
| **Legal dedupe hardening** | Backlog | Add `source_doc` to `_register_dedupe_key` |
| **Legal R-2 (t4c variance)** | Deferred / accepted | Post-fix e2e **7/11** (≥7 floor); LLM entity-resolution variance |
| **T9 `.docx` on serverless** | Open (infra) | Missing `python-docx`; `.md` memo + exec-summary OK |
| **phv4 NEW-1** | Open | Test `ec74042` insurance BACKGROUND filter — sound fix, behavior untested |

---

## Closed (do not re-do)

SQLite provenance (Phases 1–3), BMA R-1/R-3, Elder Care DAG e2e (`1074138209208842`, `827597669988464`), Profiler 7/7, Chip B 4-company e2e, G6 gold bootstrap (57 labels), G5 VDR gate, FTA memo `flags` parse fix, Hector merge (2026-08-03). Detail: `OPEN_ITEMS.md` closed section + `.dev/archive/sqlite_removal.md`.

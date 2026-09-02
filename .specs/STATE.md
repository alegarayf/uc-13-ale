# STATE

## Decisions

### AD-001
- **Decision**: Toda llamada de chat/visión a un LLM en `databricks/` se enruta por `agents/shared/llm_client.py`; ningún módulo nuevo construye su propio `mlflow.deployments` deploy client para un endpoint de Claude. Los embeddings quedan explícitamente exentos.
- **Reason**: Antes de esta feature el mismo patrón `client.predict()` estaba replicado en 11 archivos, lo que hacía imposible cambiar de proveedor, instrumentar tracing o añadir fallback sin 11 ediciones coordinadas. Un único punto de entrada convierte el proveedor en configuración.
- **Trade-off**: Se introduce una capa de indirección entre el agente y el modelo, y una tabla de mapeo alias→model ID que hay que mantener cuando se añada un modelo. A cambio, los call sites conservan su firma actual y los YAMLs de workflow no cambian.
- **Scope**: `databricks/agents/**`, `databricks/jobs/scripts/**`. Exento: todo call site de embeddings (`retrieval.py`, `ingestion_parser.get_embeddings_batch`, `doc_worker.py`, `ensure_coverage.py`), porque Anthropic no ofrece API de embeddings.
- **Date**: 2026-09-01
- **Status**: active

## Handoff

- **Feature**: anthropic-sdk-migration (`.specs/features/anthropic-sdk-migration/`)
- **Phase / Task**: Phase 0 (gate de egress) — T1 y T2 completas y commiteadas; **T3 bloqueada**
- **Completed**: Specify, Discuss, Design, Tasks (24 tareas, gate limpio), T1 (`588aa51`), T2 (`e1b2029`)
- **In-progress** (file:line): none
- **Next step**: T3 — ejecutar `databricks/jobs/scripts/check_anthropic_egress.py` como tarea serverless en el workspace Rallyday y registrar la evidencia en `signoffs/ASDK-13-egress-gate.md`
- **Blockers**: (1) el secreto `anthropic_api_key` no está en el scope `uc13`, y el token local **no tiene el scope `secrets`** (`databricks secrets list-scopes` falla), así que Hector debe crearlo. (2) Enviar el job es una acción externa al entorno local y requiere go-ahead explícito. Acceso a jobs sí funciona (perfil `rallyday`, `jobs list` responde).
- **Uncommitted files**: none
- **Branch**: feature/anthropic-sdk-migration

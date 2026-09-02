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
- **Phase / Task**: **Phase 0 completa (T1, T2, T3).** Gate de egress PASS. Siguiente: Phase 1 (T4-T7)
- **Completed**: Specify, Discuss, Design, Tasks (24 tareas), T1 `588aa51`, T2 `e1b2029` + fix `00b08f2`, T3 (signoff `signoffs/ASDK-13-egress-gate.md`)
- **In-progress** (file:line): none
- **Next step**: T4 — crear `databricks/agents/shared/llm_client.py` con la tabla `_MODEL_MAP`, `_active_backend()` y `resolve_model()`
- **Blockers**: none para la migración. Pendiente de seguridad ajeno al plan: rotar la API key de Anthropic y `sp_client_secret`, ambos escritos en texto plano en celdas de notebook durante la carga del secreto.
- **Decisión que arrastra T3**: `anthropic 1.3.0` queda fuera del rango de `mlflow.anthropic.autolog()`, así que en T11 autolog estará desactivado y el tracing dependerá solo de los spans manuales del gateway.
- **Uncommitted files**: none
- **Branch**: feature/anthropic-sdk-migration (sin pushear)

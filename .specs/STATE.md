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
- **Phase / Task**: **Phase 1 completa (T4-T7).** Núcleo puro del gateway listo: mapeo, normalización de usage, conversión de visión, clasificación de errores. Siguiente: Phase 2 (T8-T11)
- **Completed**: Specify, Discuss, Design, Tasks, Phase 0 (T1-T3, gate PASS), Phase 1 (T4 `e5295b5`, T5 `f6b2724`, T6 `0c38b2f`, T7 pendiente de commit)
- **In-progress** (file:line): T7 implementada y verificada (`databricks/agents/shared/llm_client.py`, `tests/test_llm_client_errors.py`), falta el commit
- **Next step**: commitear T7, luego T8 (credencial + construcción del cliente Anthropic bajo lock)
- **Blockers**: none
- **Uncommitted files**: `databricks/agents/shared/llm_client.py`, `tests/test_llm_client_errors.py`, `.specs/features/anthropic-sdk-migration/tasks.md`
- **Branch**: feature/anthropic-sdk-migration (sin pushear)

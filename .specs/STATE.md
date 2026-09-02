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
- **Phase / Task**: Design completado y pendiente de aprobación del usuario; Tasks aún no iniciado
- **Completed**: Specify (spec.md, gate limpio), Discuss (context.md), Design (design.md), reconciliación spec↔design tras los hallazgos de investigación (ASDK-10 enmendado, ASDK-15 añadido, 3 assumptions nuevas, Out of Scope actualizado)
- **In-progress** (file:line): none
- **Next step**: Obtener aprobación del design y generar `tasks.md` con la fase 0 = gate de egress ASDK-13 como bloqueante
- **Blockers**: none — ASDK-13 es un gate planificado, no un bloqueo actual
- **Uncommitted files**: `.specs/STATE.md`, `.specs/features/anthropic-sdk-migration/{spec,context,design}.md`
- **Branch**: feature/anthropic-sdk-migration

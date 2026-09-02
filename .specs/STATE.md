# STATE

## Decisions

### AD-001
- **Decision**: Toda llamada de chat/visión a un LLM en `databricks/` se enruta por `agents/shared/llm_client.py`; ningún módulo nuevo construye su propio `mlflow.deployments` deploy client para un endpoint de Claude. Los embeddings quedan explícitamente exentos.
- **Reason**: Antes de esta feature el mismo patrón `client.predict()` estaba replicado en 11 archivos, lo que hacía imposible cambiar de proveedor, instrumentar tracing o añadir fallback sin 11 ediciones coordinadas. Un único punto de entrada convierte el proveedor en configuración.
- **Trade-off**: Se introduce una capa de indirección entre el agente y el modelo, y una tabla de mapeo alias→model ID que hay que mantener cuando se añada un modelo. A cambio, los call sites conservan su firma actual y los YAMLs de workflow no cambian.
- **Scope**: `databricks/agents/**`, `databricks/jobs/scripts/**`. Exento: todo call site de embeddings (`retrieval.py`, `ingestion_parser.get_embeddings_batch`, `doc_worker.py`, `ensure_coverage.py`), porque Anthropic no ofrece API de embeddings; y `document_classifier.classify_batch()` (`_CLASSIFIER_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"`), descubierto en T19 — es Llama, no Claude, y el SDK de Anthropic no puede servirlo.
- **Date**: 2026-09-01 (scope corregido 2026-09-02, T19)
- **Status**: active

### AD-002
- **Decision**: Un call site cuyo endpoint es paramétrico en tiempo de ejecución (llega vía `get_param`/widget, no hardcodeado) debe consultar `llm_client.is_claude_endpoint(endpoint)` antes de llamar a `llm_client.chat()`. Si es `False`, sigue usando el deploy client de Databricks directamente — nunca debe dejar que `chat()`/`resolve_model()` lance `ValueError` como forma de detectar que el endpoint no es Claude.
- **Reason**: Descubierto en T20 — `company_profiler.call_llm()` recibe `databricks-meta-llama-3-3-70b-instruct` (default del job standalone de Phase 1-2, `uc13_ingestion_pipeline.yml`) o `databricks-claude-sonnet-4-6` (default de `run_full_pipeline.py`, Phase 1-5) según qué entry point lo invoque. Un enrutamiento incondicional habría roto el job standalone en producción, silenciosamente, porque ningún test que use el endpoint Claude por defecto lo habría detectado.
- **Trade-off**: El call site gana una rama condicional en vez de una delegación directa de una línea. A cambio, ningún endpoint no-Claude puede romper por una migración pensada solo para Claude.
- **Scope**: Cualquier función en `databricks/agents/**` o `databricks/jobs/scripts/**` cuyo endpoint de LLM se resuelva en tiempo de ejecución desde más de un entry point con defaults distintos. No aplica a los call sites con endpoint hardcodeado a Claude (BMA, FTA, CQA, QoE, KPI, `agent_base._call_llm`) ni a los hardcodeados a otro proveedor (`document_classifier`, AD-001).
- **Date**: 2026-09-02
- **Status**: active

## Handoff

- **Feature**: anthropic-sdk-migration (`.specs/features/anthropic-sdk-migration/`)
- **Phase / Task**: **Phase 5 en curso.** T24 completa al 75% (3/4 capacidades cerradas con cita; Agent Bricks pendiente de prueba práctica). T23 pausada explícitamente por el usuario — se retoma después de T24, en sesión conjunta.
- **Completed**: Phases 0-4 completas (T1-T22). T24: documento `docs/plans/anthropic-sdk-platform-capabilities.md` (pendiente de commit)
- **In-progress** (file:line): T24 implementada (documento + investigación), falta el commit
- **Next step**: commitear T24, luego retomar T23 (corrida VDR real + verificación práctica de Agent Bricks, ambas en sesión conjunta con el usuario — implican acciones visibles en el workspace de Databricks)
- **Blockers**: T23 requiere al usuario presente — corre el job VDR real y crea un endpoint External Model + agente de Agent Bricks para cerrar la pregunta que T24 dejó abierta
- **Hallazgo de T24**: Agent Bricks no tiene API pública (404 confirmado en `/api/2.0/agent-bricks`), no hay recursos de Agent Bricks en este workspace hoy, y la documentación oficial no especifica si acepta un endpoint External Model como modelo base. Sin recursos existentes que inspeccionar, cerrarlo requiere crear uno — acción de workspace pendiente de T23.
- **Uncommitted files**: `docs/plans/anthropic-sdk-platform-capabilities.md`, `.specs/features/anthropic-sdk-migration/tasks.md`, `.specs/STATE.md`
- **Branch**: feature/anthropic-sdk-migration (sin pushear)

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
- **Phase / Task**: **Phase 2 completa (T8-T11).** Gateway completo: credencial, chat() con ambos backends, fallback automático, tracing MLflow. Siguiente: Phase 3 (T12-T17)
- **Completed**: Phase 0 (T1-T3), Phase 1 (T4-T7), Phase 2: T8 `f6536eb`, T9 `57101c8`, T10 `905dc40`, T11 `00c9627`
- **In-progress** (file:line): none
- **Next step**: T12 — extender `print_token_summary()` en `agent_base.py` con backend y degradaciones; actualizar `_ENDPOINT_PRICING` a tarifas first-party
- **Blockers**: none
- **Incidente registrado (resuelto, sin daño)**: durante T11 se ejecutó por error `git checkout HEAD~15 -- .`, sobrescribiendo el árbol de trabajo. HEAD nunca se movió; `git reset --hard HEAD` restauró todo sin pérdida de historial. Detalle completo en la nota de T11 en `tasks.md`. Lección aplicada: no volver a usar `git checkout <ref> -- .` para explorar.
- **Uncommitted files**: none
- **Branch**: feature/anthropic-sdk-migration (sin pushear)

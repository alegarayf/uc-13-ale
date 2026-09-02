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
- **Phase / Task**: **Phase 4 completa (T18-T21).** Los 8 call sites de Claude migrados (6 incondicionales, 2 condicionales por AD-002). ASDK-09 verificado. Siguiente: T22 (test de convención estático) cierra Phase 4; luego Phase 5 (T23-T24).
- **Completed**: Phase 0-3 completas. Phase 4: T18 `b2663c2`, T19 `88f5c17` (N/A documentado), T20 `c151a59` (condicional), T21 (pendiente de commit — reconciliación de conteo final a 8/8 incluida)
- **In-progress** (file:line): T21 implementada y verificada (`ingestion_parser.py`, `tests/test_ingestion_parser_vision_gateway.py`), spec.md/design.md reconciliados con el conteo final verificado (8 call sites, no 10 ni 11), falta el commit
- **Next step**: commitear T21, luego T22 — test estático que estas 2 tareas ya confirmaron indirectamente (T19/T20/T21 cada una probó que su endpoint no-Claude no toca el gateway)
- **Blockers**: none
- **Decisiones nuevas de esta fase**: AD-002 (STATE.md) — cualquier call site con endpoint paramétrico debe consultar `llm_client.is_claude_endpoint()` antes de despachar al gateway. Aplicó a T20 (company_profiler) y T21 (vision).
- **Conteo final de call sites de Claude (verificado 2026-09-02, no una resta del original de 11)**: 8 — `agent_base._call_llm`, BMA, FTA, CQA, QoE, KPI (6 incondicionales) + `company_profiler` + `ingestion_parser` vision (2 condicionales). `document_classifier` excluido (Llama). `doc_worker.py`/`ensure_coverage.py` son embeddings puros, ya exentos por AD-001.
- **Uncommitted files**: `databricks/jobs/scripts/ingestion_parser.py`, `tests/test_ingestion_parser_vision_gateway.py`, `.specs/features/anthropic-sdk-migration/{spec,design,tasks}.md`, `.specs/STATE.md`
- **Branch**: feature/anthropic-sdk-migration (sin pushear)

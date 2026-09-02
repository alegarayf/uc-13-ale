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

### AD-003
- **Decision**: cualquier dependencia Python nueva que necesite el runtime de los jobs VDR (`617196299594076`, `1064797491105862`) debe añadirse en **tres lugares**, no dos: `databricks/requirements.txt`, `databricks/pyproject.toml`, **y** el campo `environments[].spec.dependencies` de los YAMLs del job (`vdr_pipeline.yml`, `vdr_rainmaker_poc.yml`) **y** de la config en vivo de ambos jobs vía Jobs API. `requirements.txt`/`pyproject.toml` no son consultados por los jobs serverless de notebook — cada job instala paquetes exclusivamente desde su propia lista `environments[].spec.dependencies`.
- **Reason**: descubierto en T23 (2026-09-02) — la primera corrida real post-migración falló con `ModuleNotFoundError: No module named 'anthropic'` en todos los agentes, pese a que T1 había declarado `anthropic>=1.3.0` correctamente en `requirements.txt` y `pyproject.toml`. Esos dos archivos nunca fueron la fuente real de paquetes para estos jobs específicos.
- **Trade-off**: tres fuentes de verdad para declarar una dependencia, en vez de una. A cambio, el entorno local (`.venv`, tests) y el entorno de producción del job pueden divergir sin que ningún test lo detecte — no hay forma de unificarlas sin cambiar cómo Databricks resuelve dependencias para notebook tasks serverless.
- **Scope**: cualquier futura dependencia Python que un agente/script bajo `databricks/agents/**` o `databricks/jobs/scripts/**` necesite en producción, si ese código se ejecuta a través de `run_vdr_rainmaker_job` (los dos jobs VDR).
- **Date**: 2026-09-02
- **Status**: active

### AD-004
- **Decision**: en `agents/shared/llm_client.py`, `temperature` se pasa a `client.messages.create()` vía `extra_body={"temperature": temperature}` — **nunca** como kwarg directo.
- **Reason**: descubierto en T23 (2026-09-02) — `anthropic` 1.x eliminó `temperature`/`top_p`/`top_k` de la firma tipada de `messages.create()` en la migración 0.x→1.x (confirmado con `inspect.signature()` contra el SDK real instalado, y con la guía oficial de migración del SDK vía el skill `claude-api` → `python/claude-api/sdk-upgrade.md` Step 6). Pasarlo directo es `TypeError` en Python, no un rechazo 400 de la API — y **ningún test de Phase 1-4 lo detectó** porque todos mockean `client.messages.create` por completo, sin ejercer jamás la firma real del SDK.
- **Trade-off**: ninguno real — `extra_body` es exactamente el mecanismo que la propia guía de migración de Anthropic recomienda para este caso (modelo que aún acepta `temperature` server-side, y código que depende genuinamente del valor).
- **Scope**: cualquier parámetro de sampling (`temperature`, `top_p`, `top_k`) en cualquier llamada a `client.messages.create()`/`.stream()`/`.parse()` en este repo, presente o futura.
- **Lección para el proceso de testing**: un test que mockea la función exacta cuya firma se quiere validar nunca puede detectar un mismatch de firma. `tests/test_llm_client_real_sdk_call_shape.py` es el patrón correcto — construye un cliente `anthropic.Anthropic` real, intercepta solo la capa de transporte HTTP (`httpx2.MockTransport`), y deja que el método real de Python valide sus propios kwargs. Verificado como discriminador real: revertido el fix localmente, el test reprodujo el `TypeError` exacto de producción, luego restaurado.
- **Date**: 2026-09-02
- **Status**: active

## Handoff

- **Feature**: anthropic-sdk-migration (`.specs/features/anthropic-sdk-migration/`)
- **Phase / Task**: **T23 PASS (2026-09-02)** — las tres corridas de paridad cerraron en SUCCESS, el signoff está escrito y el Git folder ya se restauró a la rama de su dueño. T24 sigue al 75%. Queda un punto menor abierto en T23 (contador de degradaciones, `[~]`) y la verificación de Agent Bricks.
- **Completed**:
  - Phases 0-4 completas (T1-T22), todo commiteado y pusheado.
  - T24 commiteado (`323e156`): 3/4 capacidades de plataforma cerradas con cita; Agent Bricks explícitamente sin cerrar (ver nota abajo).
  - **T23 cerrada con PASS**: `signoffs/ASDK-12-parity.md`. Ronda 3 con el Git folder en `7e2adfd`, las tres en SUCCESS — 62 como canaria (`283330252313546`, 25.2 min), luego 63 (`447543265613924`, 29.2 min) y 64 (`619316757100307`, 30.6 min) en paralelo. Evidencia: 24/24 celdas (8 tablas × 3 compañías) con `created_at` de hoy; mismo par de artefactos que el baseline en los tres `results_location`, verificado listando directorios; `diligence_report` sin fila nueva en ninguna (las tres por ruta CIM-scoped, igual que el baseline); tokens dentro de ±6%.
  - Corrida con key inválida: **PASS**. `anthropic.AuthenticationError`, `status_code=401` emitido por los servidores de Anthropic, `fallback_count` 0 antes y después. Ejercida localmente vía el fallback a `ANTHROPIC_API_KEY` de `_resolve_api_key()`, **no** como corrida del job — inyectarla en el job exigía mutar el secreto `uc13/anthropic_api_key`, compartido con el job `1064797491105862` y producción.
  - Los dos bugs de producción (AD-003 dependencias del job en `67ae3b5`; AD-004 `extra_body` en `23e04e1`) quedaron **confirmados en ejecución real**, no solo por tests: el warning de autolog que emiten las tres corridas sale de `llm_client.py:546` leyendo `anthropic.__version__` (prueba que el paquete se importó → AD-003), y los 8 agentes × 3 compañías completaron llamadas a Claude por el gateway (prueba que `extra_body` funciona → AD-004).
  - Baseline preservado intacto: `signoffs/ASDK-12-parity-baseline-snapshot.md`; los directorios `20260826T*` del volumen no se tocaron.
  - Memoria del proyecto corregida: `uc13-catalog-convention` afirmaba que "el VDR es `uc13` hardcodeado". Falso para el job vivo — describe `run_vdr_pipeline.py`, que es legacy y no está cableado. El job corre `run_vdr_rainmaker.py` con `VDR_CATALOG = "uc13_preview"`.
- **In-progress** (file:line): nada a medias en el árbol de trabajo.
- **Next step (inmediato, en orden)**:
  1. Cerrar el único punto abierto de T23 (cosmético, no bloquea el PASS): confirmar visualmente en la consola de Databricks que la salida del driver de los tres runs **no** contiene `[llm_fallback]`. El contador es estado in-process y solo se imprime a stdout (`llm_client.py:419`); `jobs/get-run-output` devuelve `logs` vacío para estas tareas serverless, así que no hay vía API. Marcado `[~]` en `tasks.md`, no como satisfecho.
  2. Verificación práctica de Agent Bricks (T24, pendiente): crear un endpoint External Model apuntando a Anthropic (reutilizando el secreto `uc13/anthropic_api_key`) e intentar seleccionarlo como modelo base de un agente Custom LLM desde la consola — requiere al usuario, es una acción de consola sin API.
  3. Ejecutar el Verifier del skill (author ≠ verifier) sobre la feature completa antes de declararla terminada, y correr `validate_state.py`.
- **Blockers**: ninguno.
- **Hallazgo de T24 (sin resolver, no bloqueante)**: Agent Bricks no tiene API pública (404 confirmado en `/api/2.0/agent-bricks` y variantes), no hay recursos de Agent Bricks en este workspace hoy, y la documentación oficial no especifica si acepta un endpoint External Model como modelo base. Ver paso 3 arriba.
- **Recursos de Databricks tocados** (estado al pausar): Git folder `63672178662438` — **restaurado a `feature/enhancing-format-1straw-mps` @ `3230e71`**, la rama que tenía antes de esta sesión. Durante T23 estuvo en `feature/anthropic-sdk-migration` @ `7e2adfd`. Jobs `617196299594076` y `1064797491105862`: ambos con `anthropic>=1.3.0` en `environments[].spec.dependencies`, cambio permanente y correcto — **no revertir**. Warehouse `f8e7a8ed6dea21fd`: se arrancó solo para las consultas de paridad, `auto_stop_mins=10` lo apaga por sí mismo. Filas 62/63/64 de `companies_vdr_history` y las tablas `uc13_preview.analysis.*` ahora tienen datos post-migración; el baseline vive en el snapshot y en los directorios `20260826T*` del volumen.
- **Uncommitted files**: ninguno.
- **Branch**: feature/anthropic-sdk-migration

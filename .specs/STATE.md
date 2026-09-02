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
- **Phase / Task**: **T23 en curso, dos bugs de producción encontrados y corregidos en la misma sesión.** T24 completa al 75% (commiteado). Ninguna corrida VDR ha completado exitosamente todavía con el código corregido — la próxima sesión debe relanzarlas.
- **Completed**:
  - Phases 0-4 completas (T1-T22), todo commiteado y pusheado.
  - T24 commiteado (`323e156`): 3/4 capacidades de plataforma cerradas con cita; Agent Bricks explícitamente sin cerrar (ver nota abajo).
  - T23: rama pusheada a origin (`67ae3b5`, `23e04e1`); Git folder de Databricks (`63672178662438`, antes en `feature/enhancing-format-1straw-mps`, de otra persona) apuntado a `feature/anthropic-sdk-migration`, HEAD sincronizado a `23e04e1`.
  - **Bug 1 encontrado y corregido** (`67ae3b5`): los jobs VDR (`617196299594076`, `1064797491105862`) no instalan `anthropic` — su fuente de dependencias es `environments[].spec.dependencies` en la config del job, **no** `requirements.txt`/`pyproject.toml` (T1 solo tocó estos últimos). Corregido en los dos YAMLs del repo y en la config en vivo de ambos jobs vía Jobs API. Registrado como **AD-003**.
  - **Bug 2 encontrado y corregido** (`23e04e1`): `anthropic` 1.x eliminó `temperature` de la firma de `messages.create()` — pasarlo directo es `TypeError`, no un 400 de la API. Corregido con `extra_body={"temperature": temperature}` en `_call_anthropic()`. Ningún test de Phase 1-4 lo detectó porque todos mockean `client.messages.create` completo. Añadido `tests/test_llm_client_real_sdk_call_shape.py`, que construye un cliente real con transporte HTTP mockeado (no la función) — verificado como discriminador real (revertido el fix, el test reprodujo el error exacto). Registrado como **AD-004**.
  - Snapshot del baseline capturado ANTES de cualquier corrida post-migración: `signoffs/ASDK-12-parity-baseline-snapshot.md` — compañías GKF (id=62), Clearsulting (id=63), Elder Care (id=64), todas 2026-08-26, todas ruta CIM-scoped, 8/8 tablas de análisis pobladas, mismo par de artefactos (`executive_summary.pdf` + `rainmaker_opportunity_summary.html`). **El usuario designó estos tres como el baseline autoritativo** (no el `id=32` de GKF identificado inicialmente).
- **In-progress** (file:line): ninguna corrida VDR ha terminado exitosamente aún. Se lanzaron y cancelaron dos rondas completas (GKF/32, Clearsulting/63, Elder Care/64) — la primera falló por el Bug 1, la segunda por el Bug 2. El código en el Git folder ya tiene ambos fixes (HEAD=`23e04e1`), pero **no se ha relanzado una tercera ronda todavía** — se pausó aquí por límite de contexto de la sesión.
- **Next step (inmediato, en orden)**:
  1. Verificar que `databricks/agents/shared/llm_client.py` en el repo local tiene el fix de `extra_body` (confirmarlo con `grep -n "extra_body" databricks/agents/shared/llm_client.py` antes de asumir nada — la sesión anterior hizo una mutación de prueba sobre este archivo que se restauró desde backup, vale la pena una verificación extra).
  2. Relanzar las tres corridas: `POST /api/2.0/jobs/run-now` sobre `job_id=617196299594076` con `notebook_params={"record_id": "62"}`, luego `"63"`, luego `"64"` (usar los IDs del baseline designado por el usuario, no el `32` de la primera ronda).
  3. Monitorear hasta `TERMINATED` (usar el patrón de polling en background ya usado en esta sesión — no bloquear con sleeps largos en foreground).
  4. Si alguna falla, leer el traceback completo antes de asumir la causa — las dos rondas anteriores fallaron por razones que ningún test local había cubierto; no asumir que un tercer fallo es "más de lo mismo" sin leerlo.
  5. Si las tres terminan con `SUCCESS`, comparar contra `signoffs/ASDK-12-parity-baseline-snapshot.md` (8/8 tablas de análisis con fila nueva, mismo par de artefactos, `diligence_report` sin fila nueva para GKF/Clearsulting) y escribir `signoffs/ASDK-12-parity.md` con el veredicto.
  6. Ejecutar la corrida con key inválida (criterio ya corregido en `tasks.md`: debe **fallar fuerte** con `AuthenticationError`, no degradar — no esperar `[llm_fallback]`).
  7. Luego, verificación práctica de Agent Bricks (T24, pendiente): crear un endpoint External Model apuntando a Anthropic (reutilizando el secreto `uc13/anthropic_api_key`) e intentar seleccionarlo como modelo base de un agente Custom LLM desde la consola — requiere al usuario, es una acción de consola sin API.
  8. Al terminar T23: restaurar el Git folder a `feature/enhancing-format-1straw-mps` (la rama que tenía antes de esta sesión), según lo acordado con el usuario.
- **Blockers**: ninguno técnico — todo lo necesario (secreto, permisos, baseline, código corregido) ya está en su lugar. Solo falta tiempo/contexto de sesión para relanzar y verificar.
- **Hallazgo de T24 (sin resolver, no bloqueante)**: Agent Bricks no tiene API pública (404 confirmado en `/api/2.0/agent-bricks` y variantes), no hay recursos de Agent Bricks en este workspace hoy, y la documentación oficial no especifica si acepta un endpoint External Model como modelo base. Ver paso 7 arriba.
- **Recursos de Databricks tocados esta sesión** (para que la próxima sesión sepa qué ya existe): Git folder `63672178662438` (rama cambiada, pendiente de restaurar); jobs `617196299594076` y `1064797491105862` (ambos con `anthropic>=1.3.0` añadido a `environments[].spec.dependencies`, cambio permanente y correcto — no revertir); warehouse `f8e7a8ed6dea21fd` (se dejó `STOPPED` originalmente, puede haber quedado `RUNNING` tras las consultas SQL de esta sesión — verificar y detener si ya no se necesita, para no acumular costo).
- **Uncommitted files**: ninguno — todo commiteado y pusheado hasta `23e04e1`.
- **Branch**: feature/anthropic-sdk-migration (pusheada a origin, Git folder de Databricks sincronizado a HEAD)

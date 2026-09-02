# Migración a Anthropic SDK — Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/anthropic-sdk-migration/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generada por muestreo del codebase y del spec — confirmar antes de Execute. Guidelines encontradas: `pytest.ini`, `conftest.py` (stub de pyspark a nivel raíz), `AGENTS.md` (§Local limits), `databricks/pyproject.toml` (`[tool.uv] dev-dependencies`: pytest, ruff). No hay umbrales de cobertura ni CI de Python configurado — para las capas no cubiertas por guideline se aplican los defaults fuertes.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Gateway LLM (`agents/shared/llm_client.py`) — lógica de dominio | unit | Todas las ramas; 1:1 con los AC de ASDK-01..08, 10, 11; todos los edge cases listados en el spec | `tests/test_llm_client_*.py` | `databricks/.venv/bin/python -m pytest tests/test_llm_client_*.py -v` |
| Call sites migrados (`agents/workstreams/**`, `agents/shared/agent_base.py`, `jobs/scripts/**`) | unit | Que el call site delega al gateway con los argumentos exactos (endpoint, max_tokens, temperature); que no construye un deploy client de Claude | `tests/test_<modulo>_*.py` | `databricks/.venv/bin/python -m pytest tests/test_<modulo>_*.py -v` |
| Convención arquitectónica (AD-001) | unit (escaneo estático) | Ningún módulo fuera de la lista permitida de embeddings construye un deploy client para un endpoint `claude`. Precedente: `tests/test_catalog_convention.py` | `tests/test_llm_gateway_convention.py` | `databricks/.venv/bin/python -m pytest tests/test_llm_gateway_convention.py -v` |
| Scripts operativos de un solo uso (`check_anthropic_egress.py`) | unit | Solo el formato de salida y los códigos de retorno con cliente stub; la conectividad real no es testeable localmente (`AGENTS.md`: sin pyspark ni cluster local) | `tests/test_check_anthropic_egress.py` | `databricks/.venv/bin/python -m pytest tests/test_check_anthropic_egress.py -v` |
| Declaración de dependencias (`requirements.txt`, `pyproject.toml`) | none | — (build gate) | — | build gate |
| Documentos (spike ASDK-14, evidencia de signoff) | none | — (revisión humana) | — | — |

## Gate Check Commands

> Generados del codebase y **verificados ejecutándolos** antes de Execute (2026-09-01).

El intérprete es el del venv del proyecto: `databricks/.venv/bin/python`. No hay `pytest` ni `ruff` en el PATH global.

| Gate Level | When to Use | Command |
|---|---|---|
| Quick | Tras tareas con tests unitarios de un solo módulo | `databricks/.venv/bin/python -m pytest <archivo de test de la tarea> -v` |
| Full | Tras tareas que migran un call site o tocan la convención | `databricks/.venv/bin/python -m pytest tests/ -q` |
| Build | Al cerrar una fase, o tras tareas de solo configuración/documento | `databricks/.venv/bin/ruff check <archivos .py tocados por la tarea> && databricks/.venv/bin/python -m pytest tests/ -q` — si la tarea no tocó ningún `.py`, el paso de ruff se omite |

**Línea base medida antes de la primera tarea:** `1020 passed, 34 skipped`. Cualquier tarea debe dejar el total en ese número o más alto; una caída es una regresión, no ruido.

**Por qué el build gate acota ruff a los archivos tocados:** `ruff check databricks/` reporta 238 errores preexistentes en el árbol. Un gate sobre todo el directorio fallaría por código ajeno a la tarea y volvería el gate inútil. Limpiar esos 238 está fuera del alcance de esta feature.

---

## Execution Plan

Las fases corren en secuencia; dentro de cada fase las tareas corren en orden.

### Phase 0: Gate de egress (BLOQUEANTE)

Ninguna tarea de Phase 1+ arranca hasta que T3 reporte `ANTHROPIC_EGRESS_OK`.

```
T1 → T2 → T3
```

### Phase 1: Núcleo puro del gateway

Funciones sin I/O, testeables en aislamiento total.

```
T4 → T5 → T6 → T7
```

### Phase 2: Orquestación del gateway

```
T8 → T9 → T10 → T11
```

### Phase 3: Observabilidad y agentes de Phase 3/4/5

```
T12 → T13 → T14 → T15 → T16 → T17
```

### Phase 4: Call sites restantes y convención

```
T18 → T19 → T20 → T21 → T22
```

### Phase 5: Verificación end-to-end e investigación

```
T23 → T24
```

---

## Task Breakdown

### T1: Declarar la dependencia `anthropic`

**What**: Añadir `anthropic>=1.3.0` a las dependencias de runtime y de proyecto, con un comentario que registre por qué no se fija a una 0.x.
**Where**: `databricks/requirements.txt`
**Depends on**: None
**Reuses**: El bloque de comentarios existente de `requirements.txt` que documenta cada dependencia
**Requirement**: ASDK-15

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] `anthropic>=1.3.0` declarado con comentario que cita el rango probado por autolog (`0.55.0`–`0.107.1`) y por qué se acepta quedar fuera
- [x] La misma dependencia añadida a `databricks/pyproject.toml` `[project].dependencies`
- [x] `databricks/uv.lock` regenerado con `uv lock` (el lock está trackeado en git)
- [x] Gate check pasa: `1020 passed, 34 skipped` — igual a la línea base. Ruff omitido: ningún `.py` tocado

**Tests**: none
**Gate**: build
**Status**: ✅ Complete

**Commit**: `chore(deps): declare anthropic SDK dependency for the LLM gateway`

---

### T2: Script de smoke test de egress

**What**: Script que verifica, desde el runtime de Databricks, importabilidad de `anthropic`, versión instalada, compatibilidad con autolog, y una llamada real por cada model ID del mapeo.
**Where**: `databricks/jobs/scripts/check_anthropic_egress.py`
**Depends on**: T1
**Reuses**: El patrón `get_secret()` de `agents/workstreams/financial_trends_agent.py:71`
**Requirement**: ASDK-13, ASDK-15

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] Emite `ANTHROPIC_EGRESS_OK <model_id>` por cada modelo que responde
- [x] Emite `ANTHROPIC_EGRESS_BLOCKED <razón>` y sale distinto de cero ante fallo de red
- [x] Emite `ANTHROPIC_IMPORT_FAILED <error>` y sale distinto de cero si el import choca
- [x] Reporta la versión instalada de `anthropic` y si cae en el rango de autolog
- [x] Tests unitarios con cliente stub cubren las salidas y sus códigos de retorno
- [x] Gate check pasa: `14 passed`; suite completa `1034 passed, 34 skipped` (línea base 1020 + 14)
- [x] Test count: **14** tests pasan (planeados 5; se subió al escribirlos, sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**SPEC_DEVIATION**: se añadió una cuarta salida `ANTHROPIC_EGRESS_REACHABLE <model> status=<code>` para el caso en que la API responde con un status de error (401, 404). Razón: ASDK-13 AC2 solo define `BLOCKED` para "conectividad, DNS o política de red"; un status HTTP prueba que el egress **sí** funciona, y reportarlo como `BLOCKED` invertiría el único hecho que este gate existe para establecer. Sigue saliendo con código distinto de cero. Registrado como spec-precision gap en el docstring del script.

**Commit**: `feat(egress): add Anthropic connectivity and runtime smoke test`

---

### T3: Ejecutar el gate en el job serverless y registrar la evidencia

**What**: Correr T2 como tarea serverless en el workspace Rallyday y registrar la salida literal como evidencia de signoff.
**Where**: `signoffs/ASDK-13-egress-gate.md`
**Depends on**: T2
**Reuses**: El patrón upload-then-submit de `.dev/scripts/t2_databricks_submit.py` (`import_text_file()` + `submit_python()`)
**Requirement**: ASDK-13, ASDK-15

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Documento con la salida literal de stdout y el veredicto: **`OK`** (`signoffs/ASDK-13-egress-gate.md`)
- [x] Veredicto `OK` → se avanza a Phase 1; la contingencia B no se activa
- [x] Versión observada (`1.3.0`) y veredicto de autolog (`False`, fuera de rango) registrados: T11 dependerá solo de spans manuales
- [x] Gate check pasa: `1036 passed, 34 skipped`. Ruff omitido: ningún `.py` tocado

**Tests**: none
**Gate**: build
**Status**: ✅ Complete

**Salvedad registrada**: la evidencia serverless proviene del probe equivalente, no del script commiteado (la rama no está pusheada, el Git folder no lo tiene). Detalle en el signoff.

**Commit**: `docs(signoff): record ASDK-13 egress gate evidence`

---

### T4: Resolución de backend y mapeo alias → model ID

**What**: Crear el módulo del gateway con la tabla de mapeo explícita, `_active_backend()` y `resolve_model()`.
**Where**: `databricks/agents/shared/llm_client.py`
**Depends on**: T3
**Reuses**: Los nombres de endpoint documentados en `databricks/CLAUDE.md` §Endpoint names
**Requirement**: ASDK-02, ASDK-03

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Tabla `_MODEL_MAP` explícita con las dos entradas; sin derivación por manipulación de string
- [x] `resolve_model()` lanza `ValueError` nombrando el alias desconocido
- [x] `_active_backend()` lee `LLM_BACKEND`, default `anthropic`, y lanza `ValueError` nombrando los valores válidos ante uno inválido
- [x] Tests unitarios cubren: ambos aliases válidos, alias desconocido, default ausente, valor inválido de `LLM_BACKEND`, y no-derivación por string
- [x] Gate check pasa: `7 passed`; suite completa `1043 passed, 34 skipped`
- [x] Test count: **7** tests pasan (planeados 6; se sumó un caso de no-derivación por string, sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): add backend resolution and model alias mapping`

---

### T5: Normalización del `usage` de Anthropic

**What**: Función `_normalize_usage()` que convierte el `usage` del SDK a la forma que ya consumen los contadores.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T4
**Reuses**: La forma del dict que espera `accumulate_tokens()` en `agents/shared/agent_base.py:48`
**Requirement**: ASDK-11

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] `input_tokens`→`prompt_tokens`, `output_tokens`→`completion_tokens`, `total_tokens` como suma
- [x] Campos ausentes o `None` se tratan como 0 sin lanzar
- [x] Tests unitarios cubren: usage completo, usage parcial, usage vacío, campos `None` explícitos
- [x] Gate check pasa: `4 passed`; suite completa `1047 passed, 34 skipped`
- [x] Test count: 4 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): normalize Anthropic usage to the existing token counter shape`

---

### T6: Conversión de contenido de visión

**What**: Función `_to_anthropic_content()` que traduce bloques `image_url` con data-URI al bloque `image`/`base64` del SDK.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T5
**Reuses**: La forma exacta del payload de visión que hoy construye `jobs/scripts/ingestion_parser.py:757`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] Un data-URI `data:image/png;base64,...` produce `{"type":"image","source":{"type":"base64","media_type":"image/png","data":...}}`
- [x] Los bloques `text` pasan sin alterar y se preserva el orden original de los bloques
- [x] Una entrada `str` se envuelve en un único bloque `text`
- [x] Un data-URI malformado lanza `ValueError` nombrando el bloque
- [x] Tests unitarios cubren los cuatro casos, incluido el shape exacto de producción (imagen primero, texto después)
- [x] Gate check pasa: `5 passed`; suite completa `1052 passed, 34 skipped`
- [x] Test count: 5 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): convert OpenAI image_url blocks to Anthropic image blocks`

---

### T7: Clasificación de errores degradables

**What**: Función `_is_retryable(exc)` que decide si una excepción del SDK justifica degradar al backend de Databricks.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T6
**Reuses**: La tabla de estrategia de errores de `design.md` §Error Handling Strategy
**Requirement**: ASDK-05, ASDK-07

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] Devuelve `True` para `APIConnectionError`, `APITimeoutError`, `RateLimitError`, y `APIStatusError` con `status_code >= 500`
- [x] Devuelve `False` para `BadRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`
- [x] Una excepción desconocida devuelve `False` (no degradar ante lo que no se entiende)
- [x] Tests unitarios cubren cada clase de excepción nombrada (con instancias reales del SDK, no stubs), ambos lados de la frontera de status (499/500), y el caso desconocido
- [x] Gate check pasa: `14 passed`; suite completa `1066 passed, 34 skipped`
- [x] Test count: **14** tests pasan (planeados 10; se sumaron la frontera exacta 499/500 y el caso desconocido, sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Nota de diseño**: `RateLimitError` es subclase de `APIStatusError` (status 429), igual que las cuatro no-retryables (400/401/403/404). El chequeo `status_code >= 500` las excluye automáticamente sin lista de exclusión explícita — la jerarquía del SDK ya codifica la distinción, más simple que lo dibujado en `design.md`.

**Commit**: `feat(llm): classify which SDK errors justify a serving fallback`

---

### T8: Construcción del cliente y resolución de la credencial

**What**: `_get_anthropic_client()` con construcción perezosa bajo lock, y resolución de la API key desde secret scope con fallback a variable de entorno.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T7
**Reuses**: Los patrones `_get_dbutils()`, `get_secret()` y `get_param()` de `agents/workstreams/financial_trends_agent.py:60-104`
**Requirement**: ASDK-08

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] Key resuelta vía `get_secret()` sobre el scope de `get_param("anthropic_secret_scope", default="uc13")`, con fallback a `ANTHROPIC_API_KEY`
- [x] Cliente construido una sola vez por proceso, bajo `threading.Lock`, con `timeout=600` y `max_retries=2`
- [x] Sin key y con backend `anthropic`: excepción que nombra el scope y la variable, y no contiene ningún valor de secreto
- [x] Sin el paquete `anthropic` instalado y con backend `anthropic`: `ImportError` con la instrucción de instalación, sin degradar a Databricks
- [x] Tests unitarios cubren: resolución por secreto, resolución por env, scope parametrizado, ausencia de key, ausencia del paquete, y que dos llamadas devuelven la misma instancia
- [x] Gate check pasa: `8 passed`; suite completa `1074 passed, 34 skipped`
- [x] Test count: **8** tests pasan (planeados 6; se sumaron scope parametrizado y la separación explícita del caso "no filtra el secreto", sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): resolve the Anthropic credential from the Databricks secret scope`

---

### T9: `chat()` con ambas rutas de backend, sin fallback

**What**: `_call_anthropic()`, `_call_databricks()` y el `chat()` público que enruta según el backend activo. Sin degradación todavía.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T8
**Reuses**: El cuerpo de `client.predict()` existente de `agents/shared/agent_base.py:189-202` para la ruta Databricks
**Requirement**: ASDK-01, ASDK-04

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] `chat()` devuelve `(texto, usage)` con la forma del contador para ambos backends
- [x] `max_tokens` y `temperature` llegan al SDK sin recorte ni elevación
- [x] `stop_reason == "max_tokens"` devuelve el texto parcial sin lanzar
- [x] `stop_reason == "refusal"` lanza excepción nombrando `stop_details.category`
- [x] Respuesta sin bloque `text` devuelve `""` y emite advertencia
- [x] La ruta Databricks envía `user_content` sin modificar (incluida visión en formato `image_url`), sin la conversión de T6
- [x] Tests unitarios cubren ambas rutas, los tres `stop_reason`, y el paso literal de `max_tokens`/`temperature`, con instancias reales de `anthropic.types.Message`/`RefusalStopDetails`
- [x] Gate check pasa: `9 passed`; suite completa `1083 passed, 34 skipped`
- [x] Test count: 9 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): add the chat entry point with Anthropic and serving backends`

---

### T10: Fallback automático con contador y registro

**What**: Envolver la ruta Anthropic para degradar a Databricks ante error retryable, contar las degradaciones y registrarlas.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T9
**Reuses**: `_is_retryable()` de T7; el patrón de contador con lock de `agents/shared/agent_base.py:43-45`
**Requirement**: ASDK-05, ASDK-06, ASDK-07

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Error retryable degrada a Databricks y devuelve su resultado
- [x] Cada degradación emite a stdout una línea con `[llm_fallback]`, el alias del endpoint y el tipo de excepción originante
- [x] Error no retryable propaga sin intentar el fallback
- [x] Si Databricks también falla, propaga su excepción con la de Anthropic encadenada como `__cause__` (verificado por identidad de objeto)
- [x] El fallback ocurre a lo más una vez por llamada, sin bucle entre backends
- [x] `get_fallback_count()` / `reset_fallback_count()` expuestos y thread-safe (verificado con 20 hilos reales)
- [x] Tests unitarios cubren: degradación exitosa, propagación no retryable, refusal (no degrada — decisión de contenido, no caída de infra), doble fallo con causa encadenada, ausencia de bucle, y el contador bajo llamadas concurrentes
- [x] Gate check pasa: `8 passed`; suite completa `1091 passed, 34 skipped`
- [x] Test count: 8 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Commit**: `feat(llm): degrade to Databricks serving on transient Anthropic failures`

---

### T11: Instrumentación con MLflow

**What**: Span manual por llamada con atributos de backend y modelo, más activación condicional de autolog según la versión observada en T3.
**Where**: `databricks/agents/shared/llm_client.py` (modificar)
**Depends on**: T10
**Reuses**: El patrón `import mlflow` dentro de `try/except ImportError` de `agents/orchestration/pipeline.py:417`
**Requirement**: ASDK-10

> **Dato de T3 que condicionó esta tarea:** el entorno real corre `anthropic 1.3.0`, fuera del rango de autolog. La rama que se ejecuta en producción es la de "fuera de rango", así que autolog queda **inerte** y el tracing descansa enteramente en los spans manuales — confirmado, no hipotético.

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Cada llamada abre un span con `llm.endpoint_alias`, `llm.backend`, `llm.fallback_used`, `llm.max_tokens`, `llm.prompt_tokens`, `llm.completion_tokens`
- [x] La API key no aparece en ningún atributo del span
- [x] MLflow ausente o `start_span` lanzando: la llamada al modelo se completa igual y se emite advertencia
- [x] `_maybe_enable_autolog()` activa autolog una sola vez, solo si la versión de `anthropic` cae en el rango probado; fuera de rango emite advertencia nombrando la versión
- [x] Los spans se anidan bajo el span activo (usa `mlflow.start_span`, verificado por la llamada exacta — no crea un trace root nuevo)
- [x] `fallback_used` se deriva del valor devuelto por esta llamada específica, no de un diff sobre el contador global (evita atribuir a esta llamada la degradación de otro hilo bajo `ThreadPoolExecutor`)
- [x] Tests unitarios cubren: atributos del span, ausencia de la key, anidamiento, MLflow ausente, `start_span` lanzando, propagación de errores genuinos, autolog dentro/fuera de rango, autolog una sola vez, y las 5 fronteras exactas de versión
- [x] Gate check pasa: `15 passed`; suite completa `1106 passed, 34 skipped`
- [x] Test count: **15** tests pasan (planeados 7; se ampliaron con anidamiento, propagación de errores, y fronteras de versión, sin borrados silenciosos)

**Tests**: unit
**Gate**: quick
**Status**: ✅ Complete

**Incidente registrado durante esta tarea (sin impacto en el código final):** al investigar un directorio `mlruns/` no trackeado, se ejecutó por error `git checkout HEAD~15 -- .`, que sobrescribió ~55 archivos trackeados del árbol de trabajo con una versión de 15 commits atrás. `HEAD` nunca se movió (`git rev-parse HEAD` confirmó `905dc40`), así que `git reset --hard HEAD` restauró el árbol sin pérdida de historial. Costo real: se perdieron las ediciones no commiteadas de T11 en `llm_client.py` (rehechas). Al rehacerlas, un `Edit` con `old_string` que no capturó el límite completo del bloque a reemplazar dejó **dos definiciones de `chat()`** en el archivo — Python resolvía a la última (la vieja, sin tracing), y los tests fallaban silenciosamente sin ningún warning porque el wrapper nuevo nunca se ejecutaba. Detectado por los tests de tracing (`llm.endpoint_alias` ausente del span) y corregido eliminando el bloque duplicado (líneas 613-893). Lección: nunca usar `git checkout <ref> -- .` para explorar — es una operación de escritura; usar `git show <ref>:<path>` en su lugar.

**Commit**: `feat(llm): instrument gateway calls with MLflow spans`

---

### T12: Resumen de tokens con backend y degradaciones

**What**: Extender `print_token_summary()` para reportar qué backend sirvió cada endpoint y cuántas degradaciones hubo, y actualizar `_ENDPOINT_PRICING` a tarifas first-party.
**Where**: `databricks/agents/shared/agent_base.py` (modificar)
**Depends on**: T11
**Reuses**: `print_token_summary()` y `_ENDPOINT_PRICING` existentes en el mismo archivo
**Requirement**: ASDK-11, ASDK-06

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El resumen incluye el backend por endpoint y el total de degradaciones
- [x] `_ENDPOINT_PRICING` actualizado a tarifas first-party de Anthropic (confirmadas con el skill `claude-api`: Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5 — el valor previo de Haiku, $0.80/$4, era la estimación del contrato Databricks)
- [x] Las claves del breakdown siguen siendo los aliases estilo Databricks
- [x] `reset_token_counter()` invoca `llm_client.reset_fallback_count()` y `llm_client.reset_endpoint_backends()`
- [x] Tests unitarios cubren: forma del resumen con y sin degradaciones, endpoint de embeddings sin entrada en `llm_client`, estabilidad de las claves del breakdown, y el reset arrastrando el estado de `llm_client`
- [x] Gate check pasa: `10 passed`; suite completa `1116 passed, 34 skipped`
- [x] Test count: **10** tests pasan (planeados 4; ampliados por el hallazgo de diseño abajo, sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Hallazgo de diseño (resuelto, no bloqueante):** ASDK-11 AC3 pide "qué backend sirvió cada endpoint", pero `chat()` (T9) devuelve solo `(texto, usage)` — el backend real nunca sale del gateway. Leer `_active_backend()` al momento de imprimir habría sido engañoso: `LLM_BACKEND` no cambia a mitad de corrida, así que un endpoint que degradó repetidamente seguiría reportándose como `"anthropic"`. Se extendió `llm_client.py` (fuera del "Where" original de esta tarea, pero ya implicado por el propio Done-when de `reset_fallback_count()`) con `_endpoint_backends`, `get_endpoint_backends()`, `reset_endpoint_backends()`, y `_resolved_backend()` — registrado en las tres salidas de `chat()` (éxito con y sin span, y excepción), no solo la rama con tracing. `test_summary_reports_databricks_backend_after_a_fallback` es la prueba que habría fallado con la implementación ingenua.

**Commit**: `feat(llm): report backend and fallback count in the token summary`

---

### T13: Migrar `agent_base._call_llm()`

**What**: Reemplazar el cuerpo de `_call_llm()` por una delegación al gateway, conservando su firma pública.
**Where**: `databricks/agents/shared/agent_base.py` (modificar)
**Depends on**: T12
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] `_call_llm()` conserva firma y default `max_tokens=12_000`
- [x] `_get_llm_client()` eliminado (sin consumidores); `self._llm_client` en `__init__` y los imports huérfanos (`os`, `mlflow.deployments`) también removidos
- [x] `_parse_json_response()` y `_recover_truncated_json()` quedan sin modificar
- [x] Test unitario afirma que `_call_llm()` invoca al gateway con endpoint, `max_tokens` y `temperature` exactos
- [x] Gate check pasa: `1120 passed, 34 skipped` (1116 base − 2 del test viejo eliminado + 3 portados de C33 + 3 nuevos de `_call_llm`)
- [x] Test count: 3 tests nuevos en `test_agent_base_call_llm.py` + 3 portados a `test_llm_client_credentials.py` (sin pérdida neta de cobertura)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Nota de integridad de tests:** el Done-when original decía "eliminar `_get_llm_client()` junto a su test" sin más. Antes de borrar `tests/test_agent_base_llm_timeout.py`, se verificó que su cobertura del fix de timeout C33 (`1800`, no `setdefault`, override de un preset `600`) ya vivía sin testear en `llm_client._get_databricks_client()` desde T9 — todos los tests de T9-T11 la mockean por completo. Se portaron los dos casos a `test_llm_client_credentials.py` antes del borrado, para no violar la regla de integridad de tests (nunca reducir cobertura al eliminar código).

**Commit**: `refactor(agents): route WorkstreamAgent._call_llm through the LLM gateway`

---

### T14: Migrar la narrativa de Business Model Agent

**What**: Sustituir el deploy client local de `generate_business_model_assessment()` por el gateway.
**Where**: `databricks/agents/workstreams/business_model_agent.py` (modificar)
**Depends on**: T13
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El módulo ya no construye un deploy client para un endpoint `claude`
- [x] `max_tokens=3000` y el resto de argumentos conservan sus valores actuales
- [x] El fallback de dos pasadas C37 queda sin modificar (usa `self._call_llm`, ya migrado en T13; sin diff en esas líneas)
- [x] Test unitario afirma la delegación con argumentos exactos
- [x] Gate check pasa: `1122 passed, 34 skipped`
- [x] Test count: 2 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Nota**: esta llamada narrativa nunca acumulaba tokens (sin `accumulate_tokens()`) incluso antes de la migración — comportamiento preexistente preservado, no una omisión nueva.

**Commit**: `refactor(bma): route the assessment narrative through the LLM gateway`

---

### T15: Migrar la narrativa de Financial Trends Agent

**What**: Sustituir el deploy client local de la narrativa de FTA por el gateway.
**Where**: `databricks/agents/workstreams/financial_trends_agent.py` (modificar)
**Depends on**: T14
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El módulo ya no construye un deploy client para un endpoint `claude`
- [x] `max_tokens=2000` conservado
- [x] Test unitario afirma la delegación con argumentos exactos
- [x] Gate check pasa: `1124 passed, 34 skipped`
- [x] Test count: 2 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Nota**: se eliminó también `os.environ.setdefault("DATABRICKS_HTTP_TIMEOUT", "600")`, huérfano tras remover la construcción del deploy client que preparaba. Ni la narrativa ni la extracción de este agente acumulaban tokens antes de la migración — preservado igual.

**Commit**: `refactor(fta): route the assessment narrative through the LLM gateway`

---

### T16: Migrar la narrativa de Customer Quality Agent

**What**: Sustituir el deploy client local de la narrativa de CQA por el gateway.
**Where**: `databricks/agents/workstreams/customer_quality_agent.py` (modificar)
**Depends on**: T15
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El módulo ya no construye un deploy client para un endpoint `claude`
- [x] `max_tokens=3_000` conservado
- [x] Test unitario afirma la delegación con argumentos exactos
- [x] Gate check pasa: `1127 passed, 34 skipped`
- [x] Test count: **3** tests pasan (planeados 2; se sumó la preservación de `accumulate_tokens()`, que a diferencia de BMA/FTA sí existía en este call site, sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Nota**: a diferencia de BMA/FTA, esta narrativa sí llamaba `accumulate_tokens()` antes de la migración — preservado usando el `usage` real devuelto por `llm_client.chat()`. También eliminado `os.environ.setdefault("DATABRICKS_HTTP_TIMEOUT", "600")`, huérfano.

**Commit**: `refactor(cqa): route the assessment narrative through the LLM gateway`

---

### T17: Migrar la narrativa de Quality of Earnings Agent

**What**: Sustituir el deploy client local de la narrativa de QoE por el gateway.
**Where**: `databricks/agents/workstreams/quality_of_earnings_agent.py` (modificar)
**Depends on**: T16
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El módulo ya no construye un deploy client para un endpoint `claude`
- [x] `max_tokens=3_000` conservado
- [x] Test unitario afirma la delegación con argumentos exactos
- [x] Gate check pasa: `1130 passed, 34 skipped`
- [x] Test count: **3** tests pasan (planeados 2; sumada preservación de `accumulate_tokens()`, sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Nota**: mismo patrón que T16 (CQA) — narrativa troceada por secciones vía `_extract_section()`, `accumulate_tokens()` preexistente preservado, `os.environ.setdefault(...)` huérfano eliminado.

**Commit**: `refactor(qoe): route the assessment narrative through the LLM gateway`

---

### T18: Migrar la narrativa de KPI Agent

**What**: Sustituir el deploy client local de la narrativa de KPI por el gateway.
**Where**: `databricks/agents/workstreams/kpi_agent.py` (modificar)
**Depends on**: T17
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] El módulo ya no construye un deploy client para un endpoint `claude`
- [x] `max_tokens=3_000` conservado
- [x] `KPIAgentEndpoint` queda sin modificar (verificado por test dedicado, no solo por lectura)
- [x] Test unitario afirma la delegación con argumentos exactos
- [x] Gate check pasa: `1134 passed, 34 skipped`
- [x] Test count: **4** tests pasan (planeados 2; sumadas preservación de `accumulate_tokens()` y verificación de `KPIAgentEndpoint`, sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Commit**: `refactor(kpi): route the assessment narrative through the LLM gateway`

---

### T19: Migrar el clasificador de documentos — **N/A, documentado (no migrado)**

**What**: ~~Sustituir el deploy client de `classify_batch()` por el gateway.~~ **Investigación reveló que no aplica**: `_CLASSIFIER_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"` — es Llama 3.3 70B, no Claude. Enrutarlo por `llm_client.chat()` habría lanzado `ValueError` en cada llamada (`resolve_model()` no reconoce el alias) y roto la clasificación de documentos en producción.
**Where**: ningún cambio en `databricks/jobs/scripts/document_classifier.py`; documento nuevo `tests/test_document_classifier_not_migrated.py`
**Depends on**: T18
**Reuses**: N/A
**Requirement**: ASDK-09 (alcance corregido: 9 llamadas de chat, no 10)

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Confirmado con el usuario (pregunta directa) que el call site queda excluido, como embeddings
- [x] `spec.md` corregido: Goals, Out of Scope, Assumptions, la historia de ASDK-09 y su AC1, y traceability — el conteo pasa de "11 call sites" a "10 call sites de Claude"
- [x] `design.md` corregido: diagrama de arquitectura mueve `document_classifier` al subgrafo "fuera del gateway"
- [x] `STATE.md` AD-001 corregido: el scope de exención ahora nombra explícitamente al clasificador junto a embeddings
- [x] `document_classifier.py` **sin ningún cambio** — verificado con `git diff` vacío
- [x] Test dedicado afirma que `classify_batch()` sigue llamando al deploy client crudo (no al gateway) y que el endpoint sigue siendo Llama, no Claude — para que esto sea una aserción permanente, no una coincidencia del regex de T22
- [x] Gate check pasa: `1135 passed, 34 skipped`
- [x] Test count: 1 test pasa

**Tests**: unit
**Gate**: build
**Status**: ✅ Complete (como no-migración documentada)

**Hallazgo**: descubierto leyendo el código antes de migrar, no asumido de la spec. La investigación de Design había verificado el nombre de la variable `_CLASSIFIER_ENDPOINT` pero nunca su valor — gap de Knowledge Verification Chain (paso 1, codebase) que Design debió cerrar y no cerró.

**Commit**: `docs(spec): exclude the Llama-backed document classifier from the migration`

---

### T20: Migrar el perfilador de compañía — **enrutamiento condicional (hallazgo)**

**What**: Sustituir el deploy client de `company_profiler.call_llm()` por el gateway, **solo cuando el endpoint es Claude**. `llm_endpoint` es paramétrico y legítimamente resuelve a Llama (`uc13_ingestion_pipeline.yml` lo defaultea a `databricks-meta-llama-3-3-70b-instruct` para el job standalone de Phase 1-2) o a Claude (`run_full_pipeline.py` lo defaultea a `databricks-claude-sonnet-4-6` para Phase 1-5). Enrutar sin condición habría lanzado `ValueError` en el job standalone. Confirmado con el usuario: enrutamiento condicional en el call site, vía un nuevo predicado público `llm_client.is_claude_endpoint()`.
**Where**: `databricks/jobs/scripts/company_profiler.py` (modificar), `databricks/agents/shared/llm_client.py` (añade `is_claude_endpoint()`)
**Depends on**: T19
**Reuses**: `llm_client.chat()`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] `llm_client.is_claude_endpoint(endpoint)` público, basado en `_MODEL_MAP`
- [x] `call_llm()` enruta por el gateway solo si `is_claude_endpoint(endpoint)` es `True`; si no, sigue llamando al deploy client crudo exactamente como hoy
- [x] La llamada de chat (rama Claude) pasa por el gateway con `max_tokens=1500`, sin `system_prompt`
- [x] Las llamadas a `semantic_search()` y el `embedding_endpoint` quedan intactas
- [x] Test unitario afirma: rama Claude delega al gateway con argumentos exactos; rama Llama **no** toca el gateway y no lanza `ValueError`; un alias futuro desconocido también evita el gateway
- [x] Gate check pasa: `1142 passed, 34 skipped`
- [x] Test count: **7** tests pasan (4 en `test_llm_client_resolve.py` para `is_claude_endpoint`, 3 en `test_company_profiler_conditional_gateway.py`; planeados 2, sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**Hallazgo**: a diferencia de T19 (Llama hardcodeado, exclusión total), aquí el mismo call site legítimamente sirve ambos proveedores según el entry point. Confirmado con el usuario antes de implementar: enrutamiento condicional, no exclusión total ni migración incondicional. `spec.md`/`design.md` no requirieron corrección de conteo (company_profiler sigue contando como "migrado", ahora con matiz condicional documentado aquí).

**Commit**: `refactor(profiler): route company profiling through the LLM gateway conditionally`

---

### T21: Migrar la extracción de visión — **enrutamiento condicional (AD-002), como T20**

**What**: Sustituir el deploy client de la extracción de visión por el gateway **solo cuando `vision_endpoint` es Claude**. Verificado antes de tocar código (a raíz de T20): `vision_endpoint` es paramétrico, y el propio comentario del código fuente en `ingestion_parser.py` nombra `databricks-meta-llama-3-2-11b-vision-instruct` como valor válido. Enrutamiento incondicional habría lanzado `ValueError`. Aplica AD-002 directamente, sin re-preguntar al usuario (ya decidido).
**Where**: `databricks/jobs/scripts/ingestion_parser.py` (modificar)
**Depends on**: T20
**Reuses**: `llm_client.chat()`, `llm_client.is_claude_endpoint()` (T20), conversión T6 (ocurre dentro de `chat()`, no en este call site)
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: `claude-api`

**Done when**:
- [x] La llamada de visión pasa por el gateway con `max_tokens=2000` **solo si `is_claude_endpoint(vision_endpoint)`**; si no, sigue usando el deploy client crudo con el shape `image_url` original
- [x] La selección entre `_VISION_PROMPT` y `_VISION_PROMPT_FINANCIAL` queda sin modificar
- [x] `get_embeddings_batch()` queda intacto y sigue usando el deploy client (verificado por inspección de código fuente en el test, no solo lectura)
- [x] La respuesta `NO_DATA` se sigue tratando igual
- [x] Test unitario afirma la delegación con el payload de imagen sin convertir en el call site (la conversión T6 ocurre dentro de `chat()`) y que la ruta de embeddings no cambió
- [x] Gate check pasa: `1146 passed, 34 skipped`
- [x] Test count: 4 tests pasan (sin borrados silenciosos)

**Tests**: unit
**Gate**: full
**Status**: ✅ Complete

**SPEC_DEVIATION confirmada con el usuario**: la llamada original nunca especificaba `temperature` (default implícito del serving). La rama del gateway pasa `temperature=0.0` explícito, consistente con los otros 8 call sites de extracción ya migrados. La rama no-Claude conserva el comportamiento original exacto (sin `temperature` en el payload).

**Commit**: `refactor(parser): route vision extraction through the LLM gateway conditionally`

---

### T22: Test de convención del gateway (AD-001)

**What**: Escaneo estático que falla si un módulo fuera de la lista permitida de embeddings construye un deploy client para un endpoint de Claude.
**Where**: `tests/test_llm_gateway_convention.py`
**Depends on**: T21
**Reuses**: El patrón de escaneo estático de `tests/test_catalog_convention.py`
**Requirement**: ASDK-09

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Recorre `databricks/agents/` y `databricks/jobs/scripts/` y falla ante un deploy client fuera de la lista permitida, o ante un endpoint literal con `claude` fuera del gateway
- [x] Lista permitida explícita (8 archivos, verificados contra el inventario completo de T21) con comentario que explica por qué cada uno está exento
- [x] `document_classifier.classify_batch()`, `company_profiler.py` e `ingestion_parser.py` (T19/T20/T21) están en la lista con su razón documentada — afirmado por test parametrizado, no dejado como coincidencia del regex
- [x] El test pasa contra el árbol migrado
- [x] **Verificado con una violación real inyectada y removida** (no solo lectura del código): un archivo temporal con `get_deploy_client` + `predict(endpoint="databricks-claude-sonnet-4-6")` hizo fallar ambos checks con mensajes claros; removido, el árbol vuelve a pasar
- [x] Gate check pasa: `1152 passed, 34 skipped`
- [x] Test count: **6** tests pasan (planeados 3; se sumaron validación de documentación y 3 casos parametrizados de T19/T20/T21, sin borrados silenciosos)

**Tests**: unit
**Gate**: build
**Status**: ✅ Complete

**Commit**: `test(llm): enforce the gateway convention with a static scan`

---

### T23: Verificación de paridad end-to-end contra el baseline — **PASS (2026-09-02), 2 bugs de producción encontrados y corregidos**

**What**: Correr el job VDR sobre la data room de referencia con `LLM_BACKEND=anthropic` y comparar manifiesto y artefactos contra el baseline pre-migración.
**Where**: `signoffs/ASDK-12-parity.md`, `signoffs/ASDK-12-parity-baseline-snapshot.md` (ya escrito)

**Estado al pausar por límite de contexto (2026-09-02)**: ninguna corrida ha completado exitosamente aún. Dos rondas lanzadas y canceladas:
1. Ronda 1 (GKF/32, Clearsulting/63, Elder Care/64) — falló con `ModuleNotFoundError: No module named 'anthropic'` en todos los agentes. Causa: los jobs VDR instalan paquetes desde `environments[].spec.dependencies` de la config del job, **no** desde `requirements.txt`/`pyproject.toml` (T1 solo tocó estos últimos). Corregido en `67ae3b5`: ambos YAMLs del repo + config en vivo de los dos jobs vía Jobs API. Registrado como **AD-003** en `STATE.md`.
2. Ronda 2 (mismos tres, tras el fix del Bug 1) — falló con `TypeError: Messages.create() got an unexpected keyword argument 'temperature'` en cada llamada a Claude. Causa: `anthropic` 1.x eliminó `temperature` de la firma tipada de `messages.create()` en la migración 0.x→1.x — confirmado con `inspect.signature()` contra el SDK real y con la guía oficial de migración. Corregido en `23e04e1`: `extra_body={"temperature": temperature}` en `_call_anthropic()`. Ningún test de Phase 1-4 lo detectó porque todos mockean `client.messages.create` completo — se añadió `tests/test_llm_client_real_sdk_call_shape.py`, que ejerce la firma real del SDK con un transporte HTTP mockeado en vez de mockear la función. Registrado como **AD-004**.

**El baseline autoritativo fue redefinido por el usuario a mitad de tarea**: no el `record_id=32` (GKF) identificado inicialmente, sino los registros **62 (GKF), 63 (Clearsulting), 64 (Elder Care)**, todos del 2026-08-26 — snapshot completo ya capturado en `signoffs/ASDK-12-parity-baseline-snapshot.md` antes de cualquier corrida post-migración (para que una corrida nueva sobre el mismo `id` no destruya la evidencia del baseline al sobreescribir `results_location`).

**Ronda 3 (2026-09-02, la que cerró la tarea)**: relanzada con el Git folder sincronizado a `7e2adfd`. Las tres en `SUCCESS` — 62 primero como canaria (`283330252313546`, 25.2 min), luego 63 (`447543265613924`, 29.2 min) y 64 (`619316757100307`, 30.6 min) en paralelo. Evidencia completa en `signoffs/ASDK-12-parity.md`.

**Único punto abierto**: el contador de degradaciones no es observable desde la API (ver Done-when abajo). No bloquea el veredicto de paridad, que se sostiene en las 24 filas frescas y el par de artefactos idéntico.
**Depends on**: T22
**Reuses**: El manifiesto de corrida de `agents/orchestration/pipeline.py` y el listado de artefactos del volumen VDR
**Requirement**: ASDK-12

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Corrida ejecutada contra `uc13_preview`, nunca contra `uc13` — **satisfecho por construcción**: `run_vdr_rainmaker.py:51` tiene `VDR_CATALOG = "uc13_preview"` como constante única usada por ambas ramas; ningún parámetro puede desviarla. El criterio asumía que era algo a configurar durante la corrida; es una invariante del código. La confusión venía de `run_vdr_pipeline.py` (catálogo `uc13`), que es legacy y no está cableado a ningún job.
- [x] Manifiestos baseline y post-migración comparados agente por agente; ningún `SUCCESS` degradado a `FAILED` o `SKIPPED` — 24/24 celdas (8 tablas × 3 compañías) con fila de `created_at` de hoy. **Redacción corregida**: el criterio pedía que cada tabla "gane una fila nueva", pero el conteo se queda en 1 porque cada agente *reemplaza* la fila de su compañía; la evidencia de frescura es el `created_at`, no el conteo.
- [x] Mismo conjunto de artefactos producido; ninguna tabla de `analysis` con cero filas donde el baseline tenía filas — los tres `results_location` nuevos contienen el mismo par (`executive_summary.pdf` + `rainmaker_opportunity_summary.html`), verificado listando ambos directorios. `diligence_report`: GKF 0→0, Clearsulting 0→0, Elder Care 3→3 sin fila nueva (`MAX(created_at)` = 2026-08-25) → las tres por ruta CIM-scoped, igual que el baseline.
- [~] Contador de degradaciones y resumen de tokens de la corrida registrados — **tokens sí** (±6% del baseline en los tres: −2.7% / +5.4% / +1.0%). **Contador de degradaciones NO verificado**: es estado in-process y `_record_fallback()` solo lo imprime a stdout del driver (`llm_client.py:419`); no se persiste en ninguna tabla, y `jobs/get-run-output` devuelve `logs` vacío para estas tareas serverless. Requiere lectura visual de la salida del driver en la consola, buscando ausencia de `[llm_fallback]`. Un fallback no habría hecho fallar la corrida, así que el SUCCESS no prueba su ausencia.
- [x] **Corregido antes de ejecutar** (contradecía T7/T10): segunda corrida con key inválida documentada — confirma que **falla fuerte** con `AuthenticationError`, sin producir un entregable silenciosamente incompleto (la trampa de "hollow success" que `CLAUDE.md` ya documenta). No se espera `[llm_fallback]`: 401 está deliberadamente excluida del fallback desde T7 (`_is_retryable()` → `False`), y eso ya está probado exhaustivamente por 8 tests unitarios en T10. El Done-when original asumía lo contrario y quedó obsoleto en cuanto se refinó ese diseño. → **PASS**: `anthropic.AuthenticationError`, `status_code=401` emitido por los servidores de Anthropic, `fallback_count` 0 antes y después. Ejercido localmente vía el fallback a `ANTHROPIC_API_KEY` de `_resolve_api_key()` y **no** como corrida del job, porque inyectar una key inválida en el job exigía mutar el secreto `uc13/anthropic_api_key`, compartido con el job `1064797491105862` y producción.
- [x] Gate check pasa: `databricks/.venv/bin/ruff check <archivos tocados> && databricks/.venv/bin/python -m pytest tests/ -q` → `1155 passed, 34 skipped` (exit 0)

**Tests**: none
**Gate**: build

**Commit**: `docs(signoff): record ASDK-12 end-to-end parity evidence`

---

### T24: Spike de MLflow 3, Agent Bricks y Agent Evaluation

**What**: Documento con veredicto citado para las cuatro capacidades de plataforma bajo el SDK directo.
**Where**: `.specs/features/anthropic-sdk-migration/platform-capabilities.md` (movido desde `docs/plans/` — esa ruta está gitignorada, `docs/*` a nivel de repo, con nota explícita "nada que un clone necesite va aquí"; el "Where" original de esta tarea nunca verificó eso)
**Depends on**: T23
**Reuses**: Los hallazgos R-1 a R-4 de `design.md`
**Requirement**: ASDK-14

**Tools**:
- MCP: NONE
- Skill: NONE

**Done when**:
- [x] Veredicto con cita para tracing MLflow 3, publicación/registro de agentes, y `mlflow.genai.evaluate` — los tres alcanzables, con evidencia citada
- [x] Toda incompatibilidad o limitación encontrada se registra explícitamente (autolog fuera de rango, egress no verificado en el plano de Model Serving) con su ruta alternativa, en vez de omitirse
- [x] Documenta cómo se inyecta la API key de Anthropic en un endpoint de Model Serving (`environment_vars` + `{{secrets/scope/key}}`, reutilizando el secreto `uc13/anthropic_api_key` ya existente)
- [ ] **Agent Bricks NO se cierra con una prueba ejecutada** — ver nota abajo. Los tres caminos de verificación disponibles sin acción en el workspace (API REST, inventario de recursos existentes, documentación oficial) se agotaron sin resolver la pregunta.
- [x] Gate check pasa: `1152 passed, 34 skipped` (sin cambios de código, ruff sin archivos `.py` que revisar en `docs/`)

**Tests**: none
**Gate**: build
**Status**: ⚠️ Parcialmente completa — 3 de 4 capacidades cerradas con evidencia citada; Agent Bricks queda como pregunta abierta, explícitamente no resuelta (ver documento)

**Por qué Agent Bricks no se cierra hoy**: cerrarla requiere crear un endpoint External Model real (acción visible en el workspace, con costo) y configurar un agente desde la consola de Databricks — ninguna es una acción de solo lectura, y Agent Bricks no tiene API pública (confirmado: `404` en `/api/2.0/agent-bricks` y variantes). El usuario pidió explícitamente coordinar acciones de workspace junto con T23; se propone verificar esto en esa misma sesión conjunta, no fabricar una prueba que no se corrió.

**Commit**: `docs(plans): record platform capability verdicts under the Anthropic SDK`

---

## Phase Execution Map

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

Phase 0:  T1 ------→ T2 ------→ T3
Phase 1:  T4 ------→ T5 ------→ T6 ------→ T7
Phase 2:  T8 ------→ T9 ------→ T10 -----→ T11
Phase 3:  T12 -----→ T13 -----→ T14 -----→ T15 -----→ T16 -----→ T17
Phase 4:  T18 -----→ T19 -----→ T20 -----→ T21 -----→ T22
Phase 5:  T23 -----→ T24
```

Las fronteras entre fases también son aristas de dependencia:

```
T3 ------→ T4
T7 ------→ T8
T11 -----→ T12
T17 -----→ T18
T22 -----→ T23
```

Ejecución estrictamente secuencial — no hay paralelismo dentro de una fase.

---

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1: declarar dependencia | 1 declaración | ✅ Granular |
| T2: script de smoke test | 1 archivo nuevo | ✅ Granular |
| T3: ejecutar gate + evidencia | 1 documento | ✅ Granular |
| T4: resolución de backend + mapeo | 2 funciones cohesivas, 1 archivo | ✅ Granular |
| T5: normalización de usage | 1 función | ✅ Granular |
| T6: conversión de visión | 1 función | ✅ Granular |
| T7: clasificación de errores | 1 función | ✅ Granular |
| T8: cliente + credencial | 1 función | ✅ Granular |
| T9: `chat()` + dos rutas | 3 funciones cohesivas, 1 archivo | ✅ Granular |
| T10: fallback + contador | 1 envoltura + contador, 1 archivo | ✅ Granular |
| T11: instrumentación MLflow | 1 envoltura, 1 archivo | ✅ Granular |
| T12: resumen de tokens | 1 función + 1 constante, 1 archivo | ✅ Granular |
| T13–T21: migración de call sites | 1 archivo cada una | ✅ Granular |
| T22: test de convención | 1 archivo de test | ✅ Granular |
| T23: paridad e2e | 1 documento de evidencia | ✅ Granular |
| T24: spike de plataforma | 1 documento | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
|---|---|---|---|
| T1 | None | (inicio de Phase 0) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 | ✅ Match |
| T4 | T3 | T3 → T4 | ✅ Match |
| T5 | T4 | T4 → T5 | ✅ Match |
| T6 | T5 | T5 → T6 | ✅ Match |
| T7 | T6 | T6 → T7 | ✅ Match |
| T8 | T7 | T7 → T8 | ✅ Match |
| T9 | T8 | T8 → T9 | ✅ Match |
| T10 | T9 | T9 → T10 | ✅ Match |
| T11 | T10 | T10 → T11 | ✅ Match |
| T12 | T11 | T11 → T12 | ✅ Match |
| T13 | T12 | T12 → T13 | ✅ Match |
| T14 | T13 | T13 → T14 | ✅ Match |
| T15 | T14 | T14 → T15 | ✅ Match |
| T16 | T15 | T15 → T16 | ✅ Match |
| T17 | T16 | T16 → T17 | ✅ Match |
| T18 | T17 | T17 → T18 | ✅ Match |
| T19 | T18 | T18 → T19 | ✅ Match |
| T20 | T19 | T19 → T20 | ✅ Match |
| T21 | T20 | T20 → T21 | ✅ Match |
| T22 | T21 | T21 → T22 | ✅ Match |
| T23 | T22 | T22 → T23 | ✅ Match |
| T24 | T23 | T23 → T24 | ✅ Match |

Ninguna dependencia apunta a una fase posterior.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1 | Declaración de dependencias | none | none | ✅ OK |
| T2 | Script operativo | unit | unit | ✅ OK |
| T3 | Documento de evidencia | none | none | ✅ OK |
| T4 | Gateway LLM | unit | unit | ✅ OK |
| T5 | Gateway LLM | unit | unit | ✅ OK |
| T6 | Gateway LLM | unit | unit | ✅ OK |
| T7 | Gateway LLM | unit | unit | ✅ OK |
| T8 | Gateway LLM | unit | unit | ✅ OK |
| T9 | Gateway LLM | unit | unit | ✅ OK |
| T10 | Gateway LLM | unit | unit | ✅ OK |
| T11 | Gateway LLM | unit | unit | ✅ OK |
| T12 | Call site migrado (`agent_base`) | unit | unit | ✅ OK |
| T13 | Call site migrado | unit | unit | ✅ OK |
| T14 | Call site migrado | unit | unit | ✅ OK |
| T15 | Call site migrado | unit | unit | ✅ OK |
| T16 | Call site migrado | unit | unit | ✅ OK |
| T17 | Call site migrado | unit | unit | ✅ OK |
| T18 | Call site migrado | unit | unit | ✅ OK |
| T19 | Call site migrado | unit | unit | ✅ OK |
| T20 | Call site migrado | unit | unit | ✅ OK |
| T21 | Call site migrado | unit | unit | ✅ OK |
| T22 | Convención arquitectónica | unit | unit | ✅ OK |
| T23 | Documento de evidencia | none | none | ✅ OK |
| T24 | Documento | none | none | ✅ OK |

Ninguna violación. `Tests: none` aparece solo donde la matriz lo permite (declaración de dependencias y documentos).

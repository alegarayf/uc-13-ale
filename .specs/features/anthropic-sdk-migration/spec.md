# Migración a Anthropic SDK con fallback a Databricks Model Serving — Especificación

## Problem Statement

Todas las llamadas a Claude en `databricks/` pasan por Databricks Model Serving vía `mlflow.deployments.get_deploy_client("databricks").predict(...)`, replicado en 11 call sites. Esa ruta impone dos límites duros documentados en `databricks/CLAUDE.md`: un read timeout de serving de ~120s que ya obligó a partir la extracción de BMA en dos pasadas (C37), y un cap silencioso de 8,192 output tokens en Haiku 4.5 en este workspace. Además, ninguna llamada al modelo está instrumentada con MLflow tracing hoy, lo que bloquea cualquier avance hacia Mosaic AI Agent Evaluation y el stack MLflow 3.

Migrar al SDK oficial de Anthropic elimina ambos límites y abre la puerta al tracing de MLflow, pero introduce una dependencia de red externa, una credencial nueva, y un paquete con dependencias transitivas propias en un entorno serverless cuyo egress no está verificado. La migración debe ser transparente para el workflow VDR en producción.

## Goals

- [ ] Los 11 call sites de chat y visión llaman a Claude a través del SDK oficial de Anthropic usando los **mismos modelos** que hoy (Sonnet 4.6 y Haiku 4.5), sin cambios en widgets, YAMLs de workflow, ni notebooks de entrada.
- [ ] Cualquier fallo de la ruta Anthropic degrada automáticamente al serving endpoint equivalente dentro de la misma llamada, dejando registro explícito de cada degradación.
- [ ] Una corrida completa del job VDR (`617196299594076`) sobre una data room de referencia produce los mismos artefactos y las mismas tablas Delta pobladas que la corrida baseline pre-migración.
- [ ] Cada llamada al modelo emite un span de MLflow con modelo, tokens y backend usado — capacidad que hoy no existe.
- [ ] Documento de hallazgos que responde, con evidencia citada, si Agent Bricks, `log_model`/registro de agentes, y Mosaic AI Agent Evaluation siguen siendo alcanzables con el SDK directo.

## Out of Scope

| Feature | Reason |
|---|---|
| Migrar embeddings (`databricks-bge-large-en`) | Anthropic no ofrece API de embeddings. `retrieval.py`, `ingestion_parser.get_embeddings_batch`, `doc_worker.py` y `ensure_coverage.py` siguen usando el deploy client de Databricks sin cambios. Frontera dura. |
| Revertir o modificar el fallback de dos pasadas C37 en BMA | Cambiaría el comportamiento de extracción. El SDK directo elimina la causa raíz (timeout de ~120s), pero cobrar esa deuda es un cambio de comportamiento separado que requiere su propia validación de calidad. |
| Subir `max_tokens` por encima de los valores actuales en cualquier call site | Mismo motivo: es un cambio de comportamiento, no de transporte. La migración es a iso-comportamiento. |
| Cambiar de modelo (a Opus 5, Sonnet 5, etc.) | El usuario pidió explícitamente "los mismos modelos". Además Sonnet 4.6 acepta `temperature`, que los modelos 5 rechazan con 400 — cambiar de modelo rompería `temperature=0.0` en los 11 call sites. |
| Implementar Agent Bricks, `log_model`, registro de agentes o `mlflow.genai.evaluate()` | Ninguno existe hoy en el repo. Esta entrega investiga viabilidad y no introduce bloqueos; construirlos es trabajo posterior. |
| Añadir streaming, tool use, o prompt caching | Ninguno existe en la ruta actual. Son mejoras posteriores, no paridad. |
| Migrar `vs_filter_pushdown_probe.py` | Script de diagnóstico manual, no está en ninguna ruta de producción. |
| Configurar NCC / private egress en el workspace | Trabajo de infraestructura con otro owner. Si el smoke test de egress falla, se activa la ruta de contingencia documentada en `design.md` Apéndice A (External Model endpoint) en vez de detener la feature. |
| Implementar la ruta de contingencia B (External Model endpoint) | Solo se documenta como diseño ejecutable. Se implementa únicamente si ASDK-13 reporta `BLOCKED`, y en ese caso es su propia entrega. |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Semántica del fallback | Automático por llamada, con logging obligatorio de cada degradación | Decisión del usuario (context.md D-1). Prioriza continuidad operativa del job VDR sobre determinismo | y |
| Alcance de la entrega | 11 call sites: 10 de chat + 1 de visión | Decisión del usuario (context.md D-2). Es el mínimo que hace verificable "mismo funcionamiento end-to-end" | y |
| Fuente de la API key | Databricks Secret Scope vía el patrón `get_secret()` existente; nombre del scope parametrizable con `get_param("anthropic_secret_scope")` | Decisión del usuario (context.md D-3). Consistente con cómo ya se manejan las credenciales de SharePoint | y |
| Egress serverless hacia `api.anthropic.com` | Desconocido; smoke test real como gate bloqueante antes de tocar producción | Decisión del usuario (context.md D-4). No se asume conectividad | y |
| Mapeo de modelos | `databricks-claude-sonnet-4-6` ↔ `claude-sonnet-4-6`; `databricks-claude-haiku-4-5` ↔ `claude-haiku-4-5` | Convención de nombres observada en el workspace. El mapeo es una tabla explícita en código, no un `str.replace("databricks-", "")`, para que un endpoint desconocido falle ruidosamente en vez de inventar un model ID | n — validar con una llamada real en el smoke test |
| Firma pública de los call sites | Los call sites siguen pasando el string de endpoint estilo Databricks (`databricks-claude-sonnet-4-6`); el gateway traduce internamente | Evita tocar los defaults de `get_param`, los widgets de notebook, y los cuatro YAMLs de workflow. Reduce la superficie de cambio y mantiene el fallback trivial de resolver | y |
| Contabilidad de tokens | Se preserva `accumulate_tokens()` con la clave de endpoint estilo Databricks, para no romper la escritura a la tabla VDR ni `_ENDPOINT_PRICING` | La clave alimenta el resumen de costos y la columna de tokens del registro VDR. Cambiar la clave rompería consumidores existentes sin beneficio | y |
| Precios en `_ENDPOINT_PRICING` | Se actualizan a las tarifas first-party de Anthropic para las entradas Claude, y se añade una nota de que aplican solo cuando el backend es `anthropic` | Los precios actuales (Sonnet $3/$15, Haiku $0.80/$4) son estimaciones del contrato Databricks; el costo real cambia de proveedor tras la migración | n — confirmar tarifas contra la factura real tras la primera corrida |
| Ubicación del gateway | Módulo nuevo `databricks/agents/shared/llm_client.py` | `agents/shared/` ya es el lugar de la infraestructura compartida (`agent_base`, `retrieval`, `fallback`). `jobs/scripts/` ya importa desde `agents/` | y |
| Timeout del cliente Anthropic | 600s con `max_retries=2` (el default del SDK) | El SDK reintenta 429/5xx/conexión por sí solo. 600s cubre generaciones largas de 12–16K tokens sin el techo artificial del serving | y |
| Compatibilidad de `temperature=0.0` | Se mantiene tal cual | Sonnet 4.6 y Haiku 4.5 aceptan `temperature`. Es otra razón para no cambiar de modelo en esta entrega | y |
| Viabilidad de Agent Bricks con el SDK directo | Desconocida; se trata como spike con entregable documental, no como código comprometido | Agent Bricks es producto Databricks sobre modelos alojados en Databricks, y su modo "Custom LLM" aparece marcado *legacy* en la documentación actual. Prometer compatibilidad sin verificarla sería fabricar | n — es el objeto del spike ASDK-14 |
| Versión de `anthropic` a instalar | La última estable (`1.3.0`), aceptando que queda fuera del rango probado por `mlflow.anthropic.autolog()` (`0.55.0`–`0.107.1`) | La instrumentación primaria es manual y no depende de autolog (ASDK-10 enmendado). Fijar el SDK a una 0.x por una funcionalidad opcional sería pagar deuda por adelantado. ASDK-15 mide el costo real | n — ASDK-15 lo resuelve empíricamente |
| Conflicto de dependencias transitivas en serverless | Se detecta, no se previene: el gate importa `anthropic` en el runtime real antes de tocar producción | `anthropic` 1.x corre sobre `httpx2`, que puede chocar con lo que ya traen `mlflow[databricks]` y el SDK de Databricks. Predecirlo desde local no es fiable; el único entorno que da la respuesta es el cluster | n — ASDK-15 lo resuelve empíricamente |
| Qué pasa si el gate de egress falla | Se activa la contingencia B (External Model endpoint), no se cancela la feature | Databricks soporta provider `anthropic` nativo en External Models, con la key desde secret scope y el mismo `client.predict()`. Convierte un bloqueo de infraestructura en un cambio de tabla de mapeo | y |

**Open questions:** none — todas resueltas con el usuario o registradas arriba como assumption con default y rationale.

---

## Sweep de dimensiones de requisitos implícitos

Alcance Large/Complex → todas las dimensiones resueltas explícitamente.

| Dimensión | Resolución |
|---|---|
| Validación de entrada y límites | ASDK-03 (endpoint desconocido falla ruidosamente), ASDK-04 (`max_tokens` se pasa sin alterar) |
| Fallos y fallos parciales | ASDK-05, ASDK-06, ASDK-07 (fallback automático, clasificación de errores, fallo duro cuando ambos backends fallan) |
| Idempotencia / reintentos / duplicados | ASDK-06 — el fallback ocurre a lo más una vez por llamada; no hay bucle de reintento entre backends |
| Fronteras de auth y rate limits | ASDK-08 (credencial desde Secret Scope, nunca en logs), ASDK-06 (429 agotado es condición de fallback) |
| Concurrencia / orden | ASDK-09 — el gateway es thread-safe bajo el `ThreadPoolExecutor` de `pipeline.py` |
| Ciclo de vida de datos / expiración | N/A — el gateway no persiste estado; los contadores de tokens ya tienen su ciclo de vida gobernado por `reset_token_counter()` |
| Observabilidad | ASDK-10 (span MLflow por llamada), ASDK-11 (contabilidad de tokens preservada), ASDK-05 (log de cada degradación) |
| Fallo de dependencia externa | ASDK-05, ASDK-07, ASDK-13 (gate de egress) |
| Integridad de transiciones de estado | N/A — el gateway no tiene máquina de estados. Las transiciones del pipeline (`doc_status`, registro VDR) no cambian; ASDK-12 lo verifica end-to-end |

---

## User Stories

### P1: Gateway unificado con backend Anthropic ⭐ MVP

**User Story**: Como desarrollador del pipeline UC13, quiero un único módulo que encapsule toda llamada de chat a Claude, para que cambiar de proveedor sea una decisión de configuración y no una edición en 11 archivos.

**Why P1**: Sin esta abstracción, el fallback automático tendría que replicarse 11 veces y sería imposible de verificar de forma consistente.

**Acceptance Criteria**:

1. The system SHALL exponer una función `chat(system_prompt, user_content, endpoint, max_tokens, temperature)` que devuelve la tupla `(texto, usage_dict)` con la misma forma de `usage` (`prompt_tokens`, `completion_tokens`, `total_tokens`) que produce hoy el deploy client de Databricks.
2. WHEN el gateway recibe un nombre de endpoint estilo Databricks THEN el sistema SHALL traducirlo al model ID de Anthropic mediante una tabla explícita de mapeo.
3. IF el nombre de endpoint recibido no está en la tabla de mapeo THEN el sistema SHALL lanzar `ValueError` nombrando el endpoint desconocido, sin intentar derivar un model ID por manipulación de string.
4. WHERE la variable de entorno `LLM_BACKEND` está ausente o vale `anthropic` el sistema SHALL usar el SDK de Anthropic como backend primario.
5. WHERE `LLM_BACKEND` vale `databricks` el sistema SHALL usar el deploy client de MLflow como backend primario y no construir cliente de Anthropic alguno.
6. The system SHALL pasar `max_tokens` y `temperature` al SDK con exactamente los valores recibidos del call site, sin recortarlos ni elevarlos.

**Independent Test**: Test unitario con un cliente Anthropic stub — se invoca `chat()` con `endpoint="databricks-claude-sonnet-4-6"` y se afirma que el stub recibió `model="claude-sonnet-4-6"` y los `max_tokens` exactos; una segunda invocación con un endpoint inventado afirma el `ValueError`.

---

### P1: Fallback automático a los serving endpoints actuales ⭐ MVP

**User Story**: Como operador del job VDR, quiero que un fallo de la API de Anthropic no tumbe una corrida de diligencia, para que el pipeline mantenga la continuidad que tiene hoy.

**Why P1**: Es un requisito explícito del usuario y la única mitigación frente a un egress intermitente, un 429 sostenido o una caída de la API.

**Acceptance Criteria**:

1. IF una llamada al SDK de Anthropic falla con un error de conexión, timeout, 429 tras agotar reintentos, o cualquier status 5xx THEN el sistema SHALL reintentar la misma llamada contra el serving endpoint de Databricks equivalente y devolver su resultado.
2. WHEN ocurre una degradación al backend de Databricks THEN el sistema SHALL emitir a stdout una línea que contenga la subcadena `[llm_fallback]`, el nombre del endpoint y el tipo de excepción originante.
3. IF una llamada al SDK de Anthropic falla con un error no recuperable de request (400 de validación, 401 de autenticación, 403) THEN el sistema SHALL propagar la excepción sin intentar el fallback.
4. IF el backend de Databricks también falla tras una degradación THEN el sistema SHALL propagar la excepción del backend de Databricks, con la excepción original de Anthropic encadenada como causa.
5. The system SHALL intentar el fallback a lo más una vez por llamada, sin bucle de reintento alternando entre backends.
6. The system SHALL incrementar un contador global de degradaciones, legible al final de la corrida junto al resumen de tokens.

**Independent Test**: Test unitario que inyecta un cliente Anthropic stub que lanza `APIConnectionError` y un deploy client stub que responde OK — se afirma que `chat()` devuelve la respuesta de Databricks, que stdout contiene `[llm_fallback]`, y que el contador de degradaciones vale 1. Un segundo test con `BadRequestError` afirma que se propaga y el contador queda en 0.

---

### P1: Los 11 call sites migrados sin cambiar su contrato ⭐ MVP

**User Story**: Como desarrollador, quiero que todos los call sites de chat y visión pasen por el gateway, para que no queden rutas mixtas donde parte del pipeline usa un proveedor y parte otro.

**Why P1**: Una migración parcial hace que "mismo funcionamiento sin interrupción" sea imposible de verificar y deja el tracing incompleto.

**Acceptance Criteria**:

1. The system SHALL enrutar por el gateway las diez llamadas de chat: `agent_base._call_llm`, las narrativas de BMA, FTA, CQA, QoE y KPI, `document_classifier.classify_batch`, `company_profiler`, y las dos rutas restantes de extracción que hoy construyen su propio deploy client.
2. WHEN el gateway recibe contenido de visión THEN el sistema SHALL convertir el bloque `image_url` con data-URI base64 al bloque `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}` que exige el SDK de Anthropic.
3. WHILE el backend activo es `databricks` el sistema SHALL enviar el contenido de visión en el formato `image_url` original, sin la conversión.
4. The system SHALL dejar sin modificar toda llamada de embeddings, que sigue usando `mlflow.deployments` directamente.
5. The system SHALL preservar sin cambios los defaults de `get_param` para `llm_endpoint`, `extraction_endpoint` y `vision_endpoint` en los cuatro YAMLs de workflow y en los notebooks de entrada.
6. The system SHALL mantener los valores de `max_tokens` actuales de cada call site, incluido el fallback de dos pasadas C37 en BMA.

**Independent Test**: Un test estático recorre `databricks/agents/` y `databricks/jobs/scripts/`, y afirma que ningún archivo fuera de la lista permitida de embeddings construye un deploy client con un endpoint cuyo nombre contiene `claude`.

---

### P1: Credencial desde Databricks Secret Scope ⭐ MVP

**User Story**: Como operador, quiero que la API key de Anthropic se resuelva desde un Secret Scope, para que no viva en la configuración del job ni aparezca en logs.

**Why P1**: Sin credencial resuelta no hay llamada posible; y una credencial mal manejada es un incidente de seguridad.

**Acceptance Criteria**:

1. WHEN el gateway construye su cliente de Anthropic THEN el sistema SHALL resolver la API key vía `get_secret()` desde el scope nombrado por `get_param("anthropic_secret_scope")`, con fallback a la variable de entorno `ANTHROPIC_API_KEY` para desarrollo local.
2. IF no hay API key disponible por ninguna de las dos vías y `LLM_BACKEND` no es `databricks` THEN el sistema SHALL lanzar una excepción cuyo mensaje nombre el scope y la variable de entorno consultados, y que no contenga ningún valor de secreto.
3. The system SHALL construir el cliente de Anthropic a lo sumo una vez por proceso y reutilizarlo.
4. The system SHALL excluir la API key de todo log, traza, mensaje de excepción y span de MLflow.

**Independent Test**: Test unitario que ejecuta con el entorno limpio y afirma que la excepción nombra el scope y `ANTHROPIC_API_KEY`; y que con una key falsa inyectada, esa cadena no aparece en stdout ni en el mensaje de ninguna excepción emitida.

---

### P1: Gate de egress verificado en el job serverless ⭐ MVP

**User Story**: Como tech lead, quiero probar la conectividad real desde el job serverless antes de tocar código de producción, para no descubrir un bloqueo de red después de haber migrado 11 archivos.

**Why P1**: Es el único supuesto que puede invalidar la feature entera. Va primero.

**Acceptance Criteria**:

1. WHEN se ejecuta el script de smoke test como tarea serverless en el workspace Rallyday THEN el sistema SHALL emitir a stdout la subcadena `ANTHROPIC_EGRESS_OK` seguida del model ID que respondió.
2. IF la llamada falla por conectividad, DNS o política de red THEN el sistema SHALL emitir la subcadena `ANTHROPIC_EGRESS_BLOCKED` y terminar con código de salida distinto de cero.
3. The system SHALL verificar en el smoke test los dos model IDs del mapeo (`claude-sonnet-4-6` y `claude-haiku-4-5`) y reportar el resultado de cada uno por separado.
4. WHEN el smoke test corre THEN el sistema SHALL reportar la versión instalada de `anthropic` y si cae dentro del rango soportado por `mlflow.anthropic.autolog()`.
5. IF importar `anthropic` falla en el runtime serverless por un conflicto de dependencias transitivas THEN el sistema SHALL emitir la subcadena `ANTHROPIC_IMPORT_FAILED` con el error de importación y terminar con código distinto de cero.

**Independent Test**: Se envía el script vía el patrón upload-then-submit documentado en `.dev/scripts/t2_databricks_submit.py` y se lee `jobs.get_run_output()` buscando la subcadena.

---

### P2: MLflow tracing de todas las llamadas al modelo

**User Story**: Como analista de calidad, quiero que cada llamada a Claude produzca un span de MLflow, para poder evaluar el pipeline con Mosaic AI Agent Evaluation más adelante.

**Why P2**: Hoy no existe ningún tracing de LLM, así que no es paridad — es capacidad nueva. Valiosa, pero el pipeline funciona sin ella.

> **Enmendado en Design (2026-09-01), aprobado por el usuario.** La versión original hacía de `mlflow.anthropic.autolog()` el mecanismo primario. Se invirtió por dos razones verificadas: el rango de `anthropic` probado por MLflow es `0.55.0 ≤ v ≤ 0.107.1` mientras la versión actual del SDK es `1.3.0`, y autolog instrumenta únicamente la ruta Anthropic — dejaría sin traza precisamente las llamadas degradadas al backend de Databricks.

**Acceptance Criteria**:

1. WHEN el gateway ejecuta una llamada por cualquiera de los dos backends THEN el sistema SHALL abrir un span de MLflow que registre como atributos el model ID efectivo, el backend usado (`anthropic` o `databricks`), si hubo degradación, y los tokens consumidos.
2. IF MLflow no está disponible o `mlflow.start_span()` lanza THEN el sistema SHALL completar la llamada al modelo igualmente y emitir una advertencia a stdout, sin propagar el fallo de tracing.
3. WHERE la versión instalada de `anthropic` está dentro del rango soportado por `mlflow.anthropic.autolog()` el sistema SHALL activar autolog una sola vez por proceso como enriquecimiento adicional.
4. IF la versión instalada de `anthropic` está fuera de ese rango THEN el sistema SHALL omitir autolog y emitir una advertencia nombrando la versión detectada, sin degradar la instrumentación manual.
5. The system SHALL anidar los spans de LLM bajo los spans `agent::{key}` que `pipeline.py` ya abre, preservando la atribución por agente bajo el `ThreadPoolExecutor`.

**Independent Test**: Corrida local de un agente contra un stub, afirmando que el trace de MLflow contiene un span hijo por llamada con los atributos de backend y modelo poblados.

---

### P2: Contabilidad de tokens y costos preservada

**User Story**: Como operador, quiero que el resumen de tokens y costos siga funcionando tras la migración, para no perder la visibilidad de gasto que ya tengo.

**Why P2**: El pipeline produce sus deliverables aunque la contabilidad falle, pero perderla degrada la operación.

**Acceptance Criteria**:

1. WHEN una llamada se completa por el backend de Anthropic THEN el sistema SHALL mapear `usage.input_tokens` a `prompt_tokens` y `usage.output_tokens` a `completion_tokens`, y calcular `total_tokens` como su suma.
2. The system SHALL acumular los tokens bajo la clave de endpoint estilo Databricks, para que `get_token_breakdown()` y la columna de tokens del registro VDR mantengan sus claves actuales.
3. The system SHALL reportar en `print_token_summary()` qué backend sirvió cada endpoint y cuántas degradaciones ocurrieron.

**Independent Test**: Test unitario que alimenta un objeto `usage` estilo Anthropic y afirma la forma exacta del dict acumulado.

---

### P2: Paridad end-to-end verificada contra un baseline

**User Story**: Como tech lead, quiero una corrida completa del job VDR comparada contra un baseline pre-migración, para poder afirmar "sin interrupción" con evidencia y no con confianza.

**Why P2**: Es la verificación del objetivo 1, pero depende de que todo lo demás esté implementado.

**Acceptance Criteria**:

1. WHEN el job VDR corre sobre la data room de referencia tras la migración THEN el sistema SHALL poblar el mismo conjunto de tablas Delta de `analysis` que pobló la corrida baseline, sin filas cero en ninguna tabla que el baseline tuviera poblada.
2. WHEN la corrida termina THEN el sistema SHALL producir los mismos artefactos de archivo que el baseline (`executive_summary.pdf`, `rainmaker_opportunity_summary.html`, y `full_report.docx` en la rama full-room).
3. IF el manifiesto de corrida reporta cualquier agente en estado `FAILED` o `SKIPPED` que el baseline reportó como `SUCCESS` THEN la verificación SHALL considerarse fallida.
4. The system SHALL ejecutarse contra el catálogo `uc13_preview`, nunca contra `uc13`.

**Independent Test**: Comparación de dos manifiestos de corrida (baseline vs post-migración) y del listado de artefactos del volumen VDR.

---

### P3: Investigación de MLflow 3, Agent Bricks y Mosaic AI Agent Evaluation

**User Story**: Como tech lead, quiero saber con evidencia qué capacidades de la plataforma Databricks seguimos pudiendo usar tras migrar al SDK directo, para planear el trabajo siguiente sin sorpresas.

**Why P3**: Es un entregable documental que informa decisiones futuras; no bloquea la migración.

**Acceptance Criteria**:

1. The system SHALL producir un documento que responda, para cada una de las cuatro capacidades (tracing MLflow 3, Agent Bricks, publicación/registro de agentes en Model Serving, `mlflow.genai.evaluate`), si sigue siendo alcanzable con el SDK directo, con una cita a documentación oficial o a una prueba ejecutada.
2. IF alguna capacidad resulta incompatible con el SDK directo THEN el documento SHALL registrar explícitamente la incompatibilidad y la ruta alternativa, en lugar de omitirla.
3. The system SHALL documentar cómo se inyecta la API key de Anthropic en un endpoint de Model Serving que aloje un agente registrado.

**Independent Test**: Revisión del documento — cada una de las cuatro capacidades tiene un veredicto y una cita.

---

## Edge Cases

- IF `LLM_BACKEND` tiene un valor distinto de `anthropic` o `databricks` THEN el sistema SHALL lanzar `ValueError` al inicializar, nombrando los valores válidos.
- IF el paquete `anthropic` no está instalado en el runtime y el backend solicitado es `anthropic` THEN el sistema SHALL lanzar `ImportError` con la instrucción de instalación, sin degradar silenciosamente a Databricks.
- IF una respuesta de Anthropic termina con `stop_reason == "max_tokens"` THEN el sistema SHALL devolver el texto parcial tal cual, para que el recuperador de JSON truncado de `agent_base._parse_json_response()` opere igual que hoy.
- IF una respuesta de Anthropic termina con `stop_reason == "refusal"` THEN el sistema SHALL lanzar una excepción nombrando la categoría del rechazo, en lugar de devolver texto vacío que el parser de JSON interpretaría como respuesta corrupta.
- WHEN el gateway se invoca desde un hilo del `ThreadPoolExecutor` de `pipeline.py` THEN el sistema SHALL reutilizar el mismo cliente de Anthropic sin construir uno por hilo y sin condiciones de carrera en los contadores.
- IF la respuesta de Anthropic no contiene ningún bloque de tipo `text` THEN el sistema SHALL devolver cadena vacía y registrar una advertencia, replicando lo que hoy produce un `content` vacío del serving.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| ASDK-01 | P1: Gateway unificado | Tasks | In Design |
| ASDK-02 | P1: Gateway unificado | Tasks | In Design |
| ASDK-03 | P1: Gateway unificado | Tasks | In Design |
| ASDK-04 | P1: Gateway unificado | Tasks | In Design |
| ASDK-05 | P1: Fallback automático | Tasks | In Design |
| ASDK-06 | P1: Fallback automático | Tasks | In Design |
| ASDK-07 | P1: Fallback automático | Tasks | In Design |
| ASDK-08 | P1: Credencial desde Secret Scope | Tasks | In Design |
| ASDK-09 | P1: Los 11 call sites migrados | Tasks | In Design |
| ASDK-10 | P2: MLflow tracing | Tasks | In Design |
| ASDK-11 | P2: Contabilidad de tokens | Tasks | In Design |
| ASDK-12 | P2: Paridad end-to-end | Tasks | In Design |
| ASDK-13 | P1: Gate de egress | Tasks | In Design |
| ASDK-14 | P3: Investigación MLflow 3 / Agent Bricks | Tasks | In Design |
| ASDK-15 | P1: Gate de egress (verificación del runtime) | T1, T2, T3 | Implementing |

**ID format:** `ASDK-[NUMBER]`

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 15 total, 0 mapped to tasks, 15 unmapped ⚠️ (se resuelve en la fase Tasks)

---

## Success Criteria

- [ ] El smoke test de egress reporta `ANTHROPIC_EGRESS_OK` para ambos model IDs desde el job serverless.
- [ ] El mismo smoke test reporta la versión instalada de `anthropic`, si autolog la acepta, y que la importación no choca con las dependencias del runtime serverless.
- [ ] Ningún archivo fuera de la lista permitida de embeddings construye un deploy client con un endpoint que contenga `claude`.
- [ ] Una corrida completa del job VDR sobre `uc13_preview` con `LLM_BACKEND=anthropic` produce el mismo manifiesto de agentes y el mismo conjunto de artefactos que el baseline.
- [ ] Forzar el fallo de la ruta Anthropic (key inválida) hace que la misma corrida complete vía serving, con `[llm_fallback]` en los logs y el contador de degradaciones distinto de cero.
- [ ] El trace de MLflow de una corrida contiene un span por cada llamada al modelo, anidado bajo su span `agent::{key}`.
- [ ] El documento de investigación tiene un veredicto con cita para las cuatro capacidades de plataforma.

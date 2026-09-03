# ASDK-12 — Paridad end-to-end contra el baseline (T23)

**Veredicto: PASS.** Las tres corridas post-migración reproducen el baseline en estado del registro, cobertura de las 8 tablas de análisis, y el par de artefactos entregados. Las 266 llamadas al modelo se sirvieron por el SDK directo de Anthropic, con **cero degradaciones a serving**. La corrida con key inválida falla fuerte con `AuthenticationError` sin activar el fallback.

**Fecha**: 2026-09-02
**Commit ejecutado**: `7e2adfd` (Git folder de Databricks `63672178662438`, rama `feature/anthropic-sdk-migration`)
**Backend**: `LLM_BACKEND` sin definir → default `anthropic` (SDK directo)
**Baseline de comparación**: `signoffs/ASDK-12-parity-baseline-snapshot.md`
**Gate local**: `1155 passed, 34 skipped` (exit 0)

---

## Corridas

Job `617196299594076` (VDR Diligence Pipeline → notebook `run_vdr_rainmaker_job`).

| record | Compañía | run_id | Duración | Baseline | Resultado |
|---|---|---|---|---|---|
| 62 | GKF | `283330252313546` | 25.2 min | 27.4 min | SUCCESS |
| 63 | Clearsulting | `447543265613924` | 29.2 min | 27.6 min | SUCCESS |
| 64 | Elder Care | `619316757100307` | 30.6 min | 28.4 min | SUCCESS |

Se corrieron en dos olas: 62 como canaria (las dos rondas anteriores habían fallado por AD-003 y AD-004, así que un tercer fallo debía costar una corrida, no tres), y 63 + 64 en paralelo una vez que 62 cerró en SUCCESS.

`notebook_output` de las tres: `{"result": "success", "truncated": false}`.

---

## Criterio 1 — Catálogo: `uc13_preview`, nunca `uc13`

**Satisfecho por construcción, no por configuración.** `run_vdr_rainmaker.py:51` define `VDR_CATALOG = "uc13_preview"` como constante única, y ambas ramas (CIM-scoped y full-room) la usan. No hay parámetro, widget ni variable de entorno que pueda desviar esta ruta a `uc13`.

Nota de proceso: el Done-when original planteaba esto como algo a *asegurar* durante la corrida. No lo es — es una invariante del código. La confusión venía de `run_vdr_pipeline.py` (catálogo `uc13` hardcodeado), que es la entrada legacy y **no está cableada a ningún job**. El nombre del job ("VDR Diligence Pipeline") no dice cuál de las dos corre; hay que mirar el `notebook_path`.

## Criterio 2 — Ningún agente degradado de SUCCESS a FAILED/SKIPPED

Las 8 tablas de análisis tienen fila para las tres compañías, con `created_at` de la corrida de hoy:

| Tabla | GKF | Clearsulting | Elder Care |
|---|---|---|---|
| `business_model` | 19:46:45Z | 20:16:23Z | 20:18:12Z |
| `financial_trends` | 19:44:20Z | 20:14:19Z | 20:16:24Z |
| `customer_quality` | 19:43:57Z | 20:12:54Z | 20:15:34Z |
| `kpi` | 19:44:43Z | 20:14:03Z | 20:15:30Z |
| `legal` | 19:47:31Z | 20:17:13Z | 20:18:56Z |
| `quality_of_earnings` | 19:48:12Z | 20:19:11Z | 20:20:02Z |
| `forecast` | 19:49:36Z | 20:20:24Z | 20:21:24Z |
| `cross_analysis` | 19:51:30Z | 20:22:09Z | 20:23:35Z |

Un agente que hubiera fallado o quedado en SKIPPED no habría dejado fila fresca. Las 24 celdas (8 tablas × 3 compañías) tienen timestamp de hoy, así que ninguno se degradó.

**Corrección a la redacción del criterio del snapshot.** El snapshot pedía que cada tabla *"gane una fila nueva"*. El conteo no sube: se queda en 1, porque cada agente **reemplaza** la fila de su compañía en vez de acumular. La evidencia de que la fila es nueva es el `created_at`, no el conteo. El criterio se cumple en sustancia; su redacción asumía escritura por append, que no es la semántica de estas tablas. Registrado aquí en lugar de reportar un conteo que no significa lo que el criterio esperaba.

## Criterio 3 — Mismo conjunto de artefactos; ninguna tabla vacía donde el baseline tenía filas

Los tres `results_location` nuevos contienen exactamente el mismo par que el baseline — verificado listando ambos directorios, no solo contra el snapshot:

| Compañía | `results_location` nuevo | Contenido |
|---|---|---|
| GKF | `…/vdr/gkf/20260902T195354Z/` | `executive_summary.pdf` + `rainmaker_opportunity_summary.html` |
| Clearsulting | `…/vdr/clearsulting/20260902T202443Z/` | idem |
| Elder Care | `…/vdr/elder_care/20260902T202613Z/` | idem |

Ninguno contiene `full_report.docx`, consistente con la ruta CIM-scoped en las tres. Los directorios del baseline (`20260826T*`) siguen intactos.

`diligence_report`, comparado contra el baseline:

| Compañía | Baseline | Post-migración | Lectura |
|---|---|---|---|
| GKF | 0 | 0 | Ruta CIM-scoped (`run_orchestrator=False`) — esperado |
| Clearsulting | 0 | 0 | idem |
| Elder Care | 3 | 3, `MAX(created_at)` = 2026-08-25 | **No ganó fila** → corrió CIM-scoped, igual que el baseline |

El snapshot advertía que una fila nueva en Elder Care indicaría una corrida full-room, a verificar antes de llamarlo regresión. No ganó fila, así que la pregunta no se abre: la ruta fue la misma que en el baseline.

## Criterio 4 — Tokens y contador de degradaciones

| record | Baseline | Post-migración | Δ |
|---|---|---|---|
| 62 (GKF) | 426,350 | 414,966 | −2.7% |
| 63 (Clearsulting) | 470,734 | 496,212 | +5.4% |
| 64 (Elder Care) | 427,881 | 432,026 | +1.0% |

Los tres dentro de ±6% del baseline — consistente con el mismo trabajo hecho por la misma familia de modelos, sin señal de re-trabajo ni de truncamiento. `model_name` registrado en los tres: `databricks-claude-sonnet-4-6`.

**Contador de degradaciones: 0.** Verificado por MLflow, no por lectura de stdout.

El contador in-process (`get_fallback_count()`) efectivamente no se persiste — `_record_fallback()` solo imprime `[llm_fallback] <endpoint>: …` al driver (`llm_client.py:419`), y `jobs/get-run-output` devuelve `logs` vacío en tareas serverless de notebook. Pero el dato vive además en un segundo canal, estructurado: `_safe_set_span_attributes` graba `llm.fallback_used` y `llm.backend` como atributos de span en **cada** llamada (T11), y MLflow los persiste.

Consultando el experimento del notebook (`250e0a2c79064562a950a6cddb00afd2`) acotado a la ventana de las tres corridas:

```
spans de gateway con llm.fallback_used : 266
fallback_used                          : {'False': 266}
backend                                : {'anthropic': 266}
degradaciones                          : 0
```

Las 266 llamadas al modelo de las tres corridas se sirvieron por el SDK directo de Anthropic. Ninguna degradó a serving.

Esto es más fuerte que la lectura visual del stdout que se había planteado como única vía: cubre **toda** llamada en vez de depender de un barrido a ojo, y es reproducible. Vale la pena registrar por qué casi se cierra mal: se declaró "no observable desde la API" tras comprobar que `get-run-output` venía vacío, es decir, se buscó el dato en el canal equivocado. El diseño de tracing de T11 ya lo estaba persistiendo en otro. **Antes de declarar algo no observable, conviene revisar qué se persiste ya.**

## Criterio 5 — Key inválida: debe FALLAR FUERTE, no degradar

**PASS.** 401 real emitido por los servidores de Anthropic, propagado sin activar el fallback.

```
anthropic version   : 1.3.0
backend             : anthropic
fallback_count pre  : 0
------------------------------------------------------------------------
RESULT: FAILED HARD (expected)
  exception    : anthropic.AuthenticationError
  status_code  : 401
  message      : Error code: 401 - {'type': 'error', 'error': {'type':
                 'authentication_error', 'message': 'API key is invalid.'}}
  fallback_count post: 0

Verdict: PASS -- 401 propagated, fallback never fired, no degraded output.
```

Diseño confirmado: 401 está deliberadamente excluida del fallback desde T7 (`_is_retryable()` → `False`), y T10 lo prueba con 8 tests unitarios. Lo que esos tests **no** podían probar —porque mockean— es que una key inválida real produzca un `AuthenticationError` real por esta ruta. Eso es lo que esta prueba añade: SDK real, red real, 401 emitido por Anthropic.

`fallback_count` en 0 antes y después es la aserción que descarta la trampa de "hollow success": no basta con que lance excepción, tiene que lanzarla *sin* haber servido la respuesta por el backend de Databricks.

**Método, y por qué no fue una corrida del job.** El Done-when pedía "una segunda corrida" con key inválida. Inyectar una key inválida en el job exige apuntar `_resolve_api_key()` a otro valor, y su fuente es el secreto `uc13/anthropic_api_key` — el mismo que consumen el otro job VDR (`1064797491105862`) y producción. Mutarlo, aunque fuera temporalmente, habría puesto en riesgo corridas ajenas por una prueba de una sola aserción. Se ejerció localmente vía el fallback a `ANTHROPIC_API_KEY` del propio `_resolve_api_key()`, que recorre el mismo código de decisión (`chat()` → `_route_and_maybe_fallback()` → `_is_retryable()`). Lo que la variante local no cubre es la resolución del secreto en Databricks, que ya está ejercitada por las tres corridas en SUCCESS de arriba.

---

## Bugs de producción encontrados durante T23

Ninguno de los dos fue detectable por la suite local previa; los dos están corregidos y ahora confirmados en ejecución real.

**AD-003 — dependencias del job.** Los jobs VDR instalan paquetes desde `environments[].spec.dependencies` de su propia config, no desde `requirements.txt`/`pyproject.toml`. La ronda 1 murió con `ModuleNotFoundError: No module named 'anthropic'`. Corregido en `67ae3b5`. **Confirmado en vivo**: el warning `anthropic '1.3.0' is outside the tested range` que emiten las tres corridas sale de `llm_client.py:546` — es nuestro propio gateway leyendo `anthropic.__version__`, lo que prueba que el paquete se importó.

**AD-004 — `temperature` fuera de la firma.** `anthropic` 1.x eliminó `temperature` de la firma tipada de `messages.create()`; pasarlo directo es `TypeError`. La ronda 2 murió así en cada llamada. Corregido en `23e04e1` con `extra_body`. **Confirmado en vivo**: los 8 agentes × 3 compañías completaron llamadas a Claude por el gateway, 24/24 con fila fresca.

**Nota de proceso.** Los dos bugs comparten causa raíz de testing: la suite mockeaba `client.messages.create` por completo, así que ningún test ejercía nunca la firma real del SDK ni el entorno real del job. `tests/test_llm_client_real_sdk_call_shape.py` cierra la primera mitad (cliente real, transporte HTTP interceptado); la segunda mitad —divergencia entre el entorno local y el del job— no tiene test posible y queda como la advertencia operativa de AD-003.

---

## Limitación conocida, no defecto

`mlflow.anthropic.autolog()` se omite: `anthropic 1.3.0` queda fuera del rango probado por MLflow (0.55.0–0.107.1). Ya documentado en T24 y en `requirements.txt:21`. El tracing sigue activo por los spans manuales del gateway — el propio mensaje lo declara: *"Manual gateway spans remain the tracing mechanism."* No es una regresión de esta migración.

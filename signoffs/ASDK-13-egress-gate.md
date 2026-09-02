# ASDK-13 / ASDK-15 — Gate de egress: **PASS**

**Fecha:** 2026-09-01
**Feature:** `.specs/features/anthropic-sdk-migration/`
**Tarea:** T3 (Phase 0)
**Veredicto:** `OK` — se avanza a Phase 1. La ruta de contingencia B (External Model endpoint, `design.md` Apéndice A) **no se activa**.

---

## Evidencia

### Corrida en serverless (la que decide el gate)

Notebook del workspace Rallyday_Partners_LLC, compute **Serverless** — el mismo plano de cómputo que el job VDR `617196299594076` (`notebook_task` serverless).

```
ANTHROPIC_SDK_VERSION 1.3.0
ANTHROPIC_EGRESS_OK claude-sonnet-4-6
ANTHROPIC_EGRESS_OK claude-haiku-4-5
exit 0
```

Credencial resuelta con `dbutils.secrets.get("uc13", "anthropic_api_key")`.

### Corrida local (confirma credencial y mapeo)

```
ANTHROPIC_SDK_VERSION 1.3.0 autolog_supported=False
ANTHROPIC_EGRESS_OK claude-sonnet-4-6
ANTHROPIC_EGRESS_OK claude-haiku-4-5
exit=0
```

---

## Qué queda resuelto

| Pregunta | Veredicto | Evidencia |
|---|---|---|
| ¿Hay egress desde serverless a `api.anthropic.com`? | **Sí** | `ANTHROPIC_EGRESS_OK` en ambos modelos, corrida serverless |
| ¿`anthropic` 1.x colisiona con las dependencias del runtime serverless? (riesgo C-4, `httpx2`) | **No** | `ANTHROPIC_SDK_VERSION 1.3.0` se imprimió: el import completó tras `%pip install` |
| ¿El mapeo alias → model ID es correcto? | **Sí** | Ambos IDs respondieron en local y en serverless. Assumption cerrada en `spec.md` |
| ¿La versión instalada cae en el rango probado por `mlflow.anthropic.autolog()`? | **No** — `1.3.0` está fuera de `0.55.0`–`0.107.1` | Corrida local: `autolog_supported=False`. Confirmado por `tests/test_check_anthropic_egress.py` (casos de frontera) |

**Consecuencia directa para T11:** autolog quedará desactivado en este entorno. La instrumentación de MLflow depende enteramente de los spans manuales del gateway. Esto valida la enmienda a ASDK-10 aprobada en Design: si autolog fuera el mecanismo primario, la migración habría terminado sin ningún tracing.

---

## Salvedades

**La evidencia serverless proviene del probe equivalente, no del script commiteado.** La rama `feature/anthropic-sdk-migration` no está pusheada, así que el Git folder no contiene aún `databricks/jobs/scripts/check_anthropic_egress.py`. La celda ejecutada replica su lógica de probe (mismos model IDs, mismo `max_tokens=16`, mismo `max_retries=0`) sin la capa de resolución de credencial, que se sustituyó por `dbutils.secrets.get` directo. Para el hecho que este gate establece — hay red y el SDK importa — la evidencia es suficiente. Si se requiere evidencia del artefacto exacto, hay que pushear y correr `databricks repos update`.

**La salida serverless no imprimió `autolog_supported`.** La celda equivalente omitía esa línea. El valor `False` para `1.3.0` está confirmado en la corrida local y por los tests de frontera, y se deriva de un rango documentado, no de una observación del cluster.

---

## Acción de seguridad pendiente (fuera del alcance de esta feature)

Durante la carga del secreto, la API key se escribió **en texto plano en el código fuente de una celda de notebook**, junto con `sp_client_secret` de SharePoint en una celda contigua. Ambos valores quedaron en el notebook y en su historial de revisiones.

Pendiente para Hector:
1. Rotar la API key de Anthropic y volver a subirla vía widget, sin que el valor toque el código.
2. Rotar `sp_client_secret` y aplicar el mismo tratamiento.
3. Limpiar el contenido de ambas celdas.

No bloquea la migración. Se registra aquí porque salió a la luz durante esta tarea y no debe perderse.

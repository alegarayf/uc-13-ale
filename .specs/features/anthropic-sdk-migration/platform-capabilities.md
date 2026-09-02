# Capacidades de plataforma bajo el SDK directo de Anthropic

**Feature**: `.specs/features/anthropic-sdk-migration/` (T24, ASDK-14)
**Fecha**: 2026-09-02
**Método**: Knowledge Verification Chain (codebase → docs del proyecto → investigación web citada → prueba ejecutada donde aplica). Cero afirmaciones sin cita o sin evidencia ejecutada.

---

## Veredicto en una línea por capacidad

| Capacidad | Veredicto | Confianza |
|---|---|---|
| Tracing MLflow 3 | **Sí, alcanzable** — ya implementado (T11), agnóstico de proveedor | Alta — evidencia ejecutada en este repo |
| Publicación/registro de agentes en Model Serving | **Sí, alcanzable, con una advertencia de red no verificada** | Media-alta — documentado, no probado end-to-end en este workspace |
| `mlflow.genai.evaluate()` (Mosaic AI Agent Evaluation) | **Sí, alcanzable** — opera sobre traces, agnóstico de qué SDK los produjo | Alta — documentación oficial explícita |
| Agent Bricks | **No determinado — requiere prueba práctica**, no se cierra hoy | Ninguna — ver §4 |

---

## 1. Tracing MLflow 3 — Sí, alcanzable

**Ya construido y verificado en este repo**, no es una promesa a futuro. `agents/shared/llm_client.py` (T11) abre un span de MLflow por cada llamada, con atributos `llm.endpoint_alias`, `llm.backend`, `llm.fallback_used`, `llm.max_tokens`, `llm.prompt_tokens`, `llm.completion_tokens`, anidado bajo el span `agent::{key}` que `pipeline.py` ya abre. Verificado con 15 tests en `tests/test_llm_client_tracing.py`, incluida la ausencia de MLflow (degrada sin bloquear la llamada) y la propagación de errores genuinos.

**Lo que no funciona en este entorno, y por qué no importa:** `mlflow.anthropic.autolog()` — el mecanismo "automático" de MLflow para instrumentar el SDK de Anthropic — está probado solo contra `anthropic 0.55.0`–`0.107.1` ([MLflow — Tracing Anthropic](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/anthropic)). Este proyecto corre `anthropic==1.3.0`, fuera de ese rango — confirmado en el gate de egress de T3 (`signoffs/ASDK-13-egress-gate.md`), no supuesto. Por eso la instrumentación primaria del gateway es manual (spans propios), y `autolog()` queda como enriquecimiento opcional que se activa solo si la versión instalada cae en rango (`llm_client._maybe_enable_autolog()`).

**Consecuencia práctica:** el tracing no depende de que Anthropic o MLflow certifiquen la combinación de versiones exacta. Funciona hoy, con o sin `autolog()`.

---

## 2. Publicación y registro de agentes en Model Serving — Sí, alcanzable

### Cómo se inyecta la API key de Anthropic (requisito explícito de T24)

Model Serving soporta variables de entorno respaldadas por secretos, con la sintaxis `{{secrets/scope/key}}`, en el campo `environment_vars` de cada served entity:

```json
{
  "name": "endpoint-name",
  "config": {
    "served_entities": [{
      "entity_name": "model-name",
      "entity_version": "1",
      "environment_vars": {
        "ANTHROPIC_API_KEY": "{{secrets/uc13/anthropic_api_key}}"
      }
    }]
  }
}
```

Fuente: [Databricks — Configure access to resources from model serving endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/store-env-variable-model-serving). El secreto `uc13/anthropic_api_key` que este proyecto ya usa (T8, `llm_client._resolve_api_key()`) es directamente reutilizable aquí — mismo scope, mismo mecanismo de referencia.

Un agente registrado (por ejemplo `KPIAgentEndpoint`, el wrapper `ResponsesAgent` ya definido en `kpi_agent.py:1940` pero nunca desplegado) importaría `agents.shared.llm_client` dentro de su `predict()`, y `_get_anthropic_client()` resolvería la key desde esta variable de entorno igual que hoy la resuelve desde el secret scope en un job cluster — sin cambios de código en `llm_client.py`.

### La advertencia que no puedo cerrar sin una corrida real

El código servido corre en un **plano de cómputo distinto** al de un job cluster: un contenedor de serving en tiempo real, no un cluster de job. La documentación confirma que Model Serving admite egress a APIs externas mediante "network policies" configurables, con **acceso completo (Full access) como opción por defecto salvo que el workspace haya restringido el egress serverless** ([Databricks — Manage network policies for serverless egress control](https://docs.databricks.com/aws/en/security/network/serverless-network-security/manage-network-policies)); cuando el egress está restringido, el DNS del proveedor externo debe añadirse explícitamente a la política de red.

El gate de T3 (`signoffs/ASDK-13-egress-gate.md`) confirmó egress a `api.anthropic.com` desde un **job serverless**, no desde un endpoint de Model Serving. Es razonable esperar el mismo resultado — las políticas de egress serverless son a nivel de workspace, no por producto — pero no está **probado** para este plano de cómputo específico. No lo afirmo como hecho verificado; lo dejo como una extrapolación de alta confianza, no como una prueba ejecutada.

**Siguiente paso concreto** (fuera del alcance de T24, propuesto para cuando se retome T23 con el usuario): desplegar `KPIAgentEndpoint` a un endpoint de Model Serving real, con la key inyectada como arriba, y confirmar una predicción exitosa.

---

## 3. `mlflow.genai.evaluate()` (Mosaic AI Agent Evaluation) — Sí, alcanzable

MLflow Tracing (la base sobre la que opera `genai.evaluate()`) es explícitamente agnóstico de proveedor: "MLflow Tracing integrates with all LLM providers and AI agent frameworks... free from vendor lock-in" ([MLflow — Tracing](https://mlflow.org/docs/latest/genai/tracing/)). La evaluación opera sobre **traces ya generados**, no sobre el proveedor que los produjo — un trace que contiene los spans manuales de `llm_client.chat()` (§1) es un insumo válido para `mlflow.genai.evaluate()` exactamente igual que un trace producido por `mlflow.deployments`.

No hay una dependencia oculta de "debe ser un modelo servido por Databricks" en la superficie pública de esta API — la documentación de Databricks sobre evaluar y monitorear agentes bajo MLflow 3 ([Databricks — Evaluate and monitor agents](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/)) describe el flujo en términos de traces y scorers, no de proveedor del modelo.

**No verificado con una corrida real** de `mlflow.genai.evaluate()` sobre un trace de este pipeline — es una lectura de documentación, marcada como tal. La confianza es alta porque la arquitectura (evaluación sobre traces) hace estructuralmente difícil que dependa del proveedor, pero no es lo mismo que haberlo ejecutado.

---

## 4. Agent Bricks — No determinado

Esta es la pregunta que el spec (ASDK-14) identificó desde el spike de Design como la de mayor incertidumbre, y **sigue sin resolverse hoy** — no por falta de esfuerzo, sino porque los tres caminos de verificación disponibles se agotaron sin dar una respuesta:

1. **API de Databricks**: no existe un endpoint REST público bajo `/api/2.0/agent-bricks` ni similar — probado directamente contra el workspace (`404 Not Found` en ambos intentos, 2026-09-02).
2. **Inventario del workspace**: cero recursos de Agent Bricks existen hoy en este workspace — `GET /api/2.0/serving-endpoints` no muestra ningún endpoint `external_model` ni ningún endpoint con el patrón de nombres típico de Agent Bricks (`ka-*`, `mas-*`, etc.). No hay nada que inspeccionar.
3. **Documentación oficial**: consultada directamente ([Databricks — Agent Bricks overview](https://developers.databricks.com/docs/agents/overview), [Databricks — Custom LLM](https://docs.databricks.com/aws/en/agents/agent-bricks/custom-llm)) — ninguna de las dos páginas especifica qué tipos de serving endpoint acepta Agent Bricks como modelo base. Ambas confirman que Agent Bricks "se llama a través de un Model Serving endpoint", pero no si ese endpoint puede ser un External Model (Anthropic) o debe ser un Foundation Model API de Databricks.

**Lo que sí se sabe con certeza:** Model Serving soporta External Models con provider `anthropic` nativo ([Databricks — External models in Model Serving](https://docs.databricks.com/aws/en/generative-ai/external-models/), hallazgo R-3 de `design.md`) — arquitectónicamente, un External Model endpoint **es** un Model Serving endpoint como cualquier otro. Que Agent Bricks lo acepte como su modelo base es plausible por esa razón, pero plausible no es lo mismo que confirmado, y T24 exige explícitamente que esta pregunta se cierre con una prueba ejecutada, no con una inferencia arquitectónica.

**Por qué no se cierra hoy:** cerrarla requiere crear un endpoint External Model real (una acción visible en el workspace, con costo asociado) y luego configurar un agente de Agent Bricks desde la consola de Databricks apuntándolo a ese endpoint — ninguna de las dos cosas es una acción de solo lectura, y la segunda no tiene API pública, solo consola. Es exactamente el tipo de acción que el usuario pidió coordinar junto con T23.

**Propuesta concreta**: verificar esto como parte de la sesión conjunta de T23 — crear el endpoint External Model (reutilizando el secreto `uc13/anthropic_api_key` ya existente) y, desde la consola, intentar seleccionarlo como modelo base al crear un agente Custom LLM de Agent Bricks. Es una prueba de ~10 minutos que responde la pregunta de forma definitiva, en vez de dejarla como una suposición razonable.

---

## Resumen para decisiones futuras

- El trabajo de esta migración (T1–T22) **no bloquea** ninguna de las tres primeras capacidades — ya están alcanzables o casi verificadas.
- Agent Bricks es la única incógnita real, y **no es una incógnita que el código de esta migración pueda resolver** — es una pregunta de producto/plataforma que solo la consola de Databricks puede responder.
- Ninguna de las cuatro capacidades requiere revertir ni modificar el gateway (`llm_client.py`) construido en Phase 1-2. El diseño de spans manuales (§1) fue, de hecho, la decisión correcta para no depender de una combinación de versiones de `autolog()` fuera de nuestro control.

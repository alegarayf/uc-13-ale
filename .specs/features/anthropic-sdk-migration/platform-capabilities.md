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
| Agent Bricks | **Resuelto disolviendo la premisa**: el tipo "Custom LLM" no existe en la consola de este workspace, así que no hay selector de modelo base que aceptar o rechazar un External Model. La ruta compatible es "Code your own agent", donde el código controla el cliente y `llm_client.chat()` sirve tal cual | Alta — inspección de consola ejecutada + endpoint External Model creado y consultado end-to-end; ver §4 |

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

> **Actualización 2026-09-02 — el destino de despliegue cambió en la plataforma.** Al verificar la documentación vigente: *"Deploying a custom agent to its own Model Serving endpoint with `agents.deploy()` is a legacy path"* ([Databricks — Custom agent endpoints](https://developers.databricks.com/docs/agents/custom-agents)). Databricks ahora recomienda **Databricks Apps**; la Supervisor API (Beta) figura deprecada. El "siguiente paso" de arriba apuntaría a una ruta que la plataforma está retirando — **decidir el destino antes de invertir en desplegar.** Análisis completo en `evaluation-readiness.md`.

---

## 3. `mlflow.genai.evaluate()` (Mosaic AI Agent Evaluation) — Sí, alcanzable

MLflow Tracing (la base sobre la que opera `genai.evaluate()`) es explícitamente agnóstico de proveedor: "MLflow Tracing integrates with all LLM providers and AI agent frameworks... free from vendor lock-in" ([MLflow — Tracing](https://mlflow.org/docs/latest/genai/tracing/)). La evaluación opera sobre **traces ya generados**, no sobre el proveedor que los produjo — un trace que contiene los spans manuales de `llm_client.chat()` (§1) es un insumo válido para `mlflow.genai.evaluate()` exactamente igual que un trace producido por `mlflow.deployments`.

No hay una dependencia oculta de "debe ser un modelo servido por Databricks" en la superficie pública de esta API — la documentación de Databricks sobre evaluar y monitorear agentes bajo MLflow 3 ([Databricks — Evaluate and monitor agents](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/)) describe el flujo en términos de traces y scorers, no de proveedor del modelo.

**No verificado con una corrida real** de `mlflow.genai.evaluate()` sobre un trace de este pipeline — es una lectura de documentación, marcada como tal. La confianza es alta porque la arquitectura (evaluación sobre traces) hace estructuralmente difícil que dependa del proveedor, pero no es lo mismo que haberlo ejecutado.

---

## 4. Agent Bricks — Resuelto (2026-09-02), disolviendo la premisa de la pregunta

**Veredicto: la pregunta original —"¿acepta Agent Bricks un endpoint External Model de Anthropic como modelo base de un agente Custom LLM?"— no tiene respuesta porque el tipo de agente que presupone no existe en la consola de este workspace.** Y para lo que la migración necesita, la respuesta práctica es que Agent Bricks no le estorba: el único camino "Custom" que la consola ofrece hoy es precisamente el que deja el cliente del modelo en manos del código.

### Lo que se ejecutó

**(a) El endpoint External Model funciona.** Creado vía API y consultado end-to-end:

```
POST /api/2.0/serving-endpoints
  name              : asdk-14-anthropic-external-test
  external_model    : { name: "claude-sonnet-4-6", provider: "anthropic",
                        task: "llm/v1/chat" }
  anthropic_config  : { anthropic_api_key: "{{secrets/uc13/anthropic_api_key}}" }
  → state.deployment: DEPLOYMENT_READY

POST /serving-endpoints/asdk-14-anthropic-external-test/invocations
  → { "model": "claude-sonnet-4-6", "choices": [{ "message":
      { "content": "EXTERNAL_MODEL_OK" }}], "usage": { "total_tokens": 26 }}
```

Esto convierte en hecho verificado lo que antes era inferencia arquitectónica (hallazgo R-3 de `design.md`): Model Serving sirve Anthropic vía External Models **en este workspace**, reutilizando el secreto `uc13/anthropic_api_key` ya existente, sin duplicarlo ni rotarlo.

Detalle operativo que vale registrar: la resolución del secreto la hace el plano de serving, no la credencial del llamante. El token que creó el endpoint **no** tiene el scope `secrets` (`databricks secrets list-secrets uc13` → `Provided access token does not have required scopes: secrets`) y el endpoint resolvió la key igual. Así que no hace falta ampliar permisos de un token para montar un External Model.

**(b) No existe el tipo de agente "Custom LLM".** Inspección del diálogo *Create new Agent* (consola, 2026-09-02). La vista `All` ofrece siete tipos:

| Tipo | Naturaleza |
|---|---|
| Supervisor Agent | Gestionado por Databricks |
| Knowledge Assistant | Gestionado por Databricks |
| Genie Agent | Gestionado por Databricks |
| Information Extraction | Gestionado (`ai_extract`) |
| Document Parsing | Gestionado (`ai_parse_document`) |
| Text Classification | Gestionado (`ai_classify`) |
| **Code your own agent** | **Código propio — OSS libraries + Agent Framework** |

Bajo el filtro `Custom` queda **solo** "Code your own agent". Ningún tipo se llama "Custom LLM", y ninguno de los siete expone un selector de modelo base donde apuntar un serving endpoint arbitrario.

Es coherente con lo que ya se había leído en la documentación: la página [Custom LLM](https://docs.databricks.com/aws/en/agents/agent-bricks/custom-llm) marcaba ese modo como *legacy*. La consola ya no lo ofrece.

**Alcance de esta afirmación**: es lo que la consola de *este* workspace muestra el 2026-09-02. No se afirma que Databricks haya retirado Custom LLM del producto a nivel global — podría ser cuestión de rollout o de entitlement. Lo verificable es que aquí no está.

### Qué significa para la migración

Los seis tipos gestionados corren sobre modelos que Databricks aloja; no hay dónde inyectar un cliente de Anthropic, con o sin External Model. Si en el futuro se quisiera un Knowledge Assistant o un Supervisor Agent, ese agente usaría un modelo de Databricks — y eso es una decisión de producto independiente de esta migración, no una regresión que la migración cause.

"Code your own agent" (OSS libraries + Agent Framework) es la ruta donde el código controla el cliente del modelo. Ahí `llm_client.chat()` funciona tal como está, sin adaptación: no hay selector de modelo base que satisfacer. **Esa es la ruta compatible, y no requiere el endpoint External Model en absoluto** — el SDK directo llama a Anthropic sin pasar por Model Serving.

El endpoint `asdk-14-anthropic-external-test` **se deja creado** en el workspace (decisión del usuario, 2026-09-02): es la vía útil si algún día se quiere que un consumidor que exige un serving endpoint de Databricks —publicación/registro de agentes (§2), o el AI Gateway— llegue a Anthropic. Para el pipeline VDR de hoy no se usa.

---

## Resumen para decisiones futuras

- El trabajo de esta migración (T1–T22) **no bloquea** ninguna de las cuatro capacidades.
- Agent Bricks quedó resuelto (§4), pero no con un sí ni un no: **el tipo de agente que la pregunta presuponía no existe en la consola de este workspace.** La ruta "Custom" que sí existe —"Code your own agent"— es justamente la que deja el cliente del modelo en el código, así que el gateway sirve sin adaptación. Los seis tipos gestionados corren sobre modelos alojados por Databricks y no admiten un cliente propio; usarlos sería una decisión de producto, no una regresión de esta migración.
- Model Serving **sí** sirve Anthropic vía External Models en este workspace — verificado creando y consultando `asdk-14-anthropic-external-test`, ya no por inferencia. El secreto `uc13/anthropic_api_key` existente sirve tal cual, y su resolución la hace el plano de serving, no la credencial del llamante.
- Ninguna de las cuatro capacidades requiere revertir ni modificar el gateway (`llm_client.py`) construido en Phase 1-2. El diseño de spans manuales (§1) fue, de hecho, la decisión correcta para no depender de una combinación de versiones de `autolog()` fuera de nuestro control.

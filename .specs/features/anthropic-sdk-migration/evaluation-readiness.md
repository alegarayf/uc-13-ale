# Informe: Agent Bricks descartado, y qué falta para LLM judges

**Para**: liderazgo técnico
**Fecha**: 2026-09-02
**Contexto**: cierre de la migración al SDK directo de Anthropic (`.specs/features/anthropic-sdk-migration/`)
**Documento hermano**: `platform-capabilities.md` (T24) — este informe lo actualiza con documentación verificada el 2026-09-02

---

## Resumen en tres frases

Agent Bricks queda descartado porque el tipo de agente que necesitaríamos —Custom LLM— está marcado *legacy* en la documentación oficial y no aparece en la consola de nuestro workspace; los seis tipos que sí existen corren sobre modelos alojados por Databricks y no admiten un cliente propio. Un framework de evaluación **sí es viable**, y no es el SDK de Anthropic lo que lo condiciona: MLflow Tracing es agnóstico de proveedor y ya tenemos traces reales aterrizando y consultables. Lo que falta es una cosa concreta y acotada: **nuestros traces no contienen el contenido de las conversaciones**, solo metadata, y sin ese contenido los LLM judges no tienen qué evaluar.

---

## 1. Por qué Agent Bricks queda descartado

### Lo que se verificó, no lo que se supuso

La pregunta original era: *¿acepta Agent Bricks un endpoint External Model de Anthropic como modelo base de un agente Custom LLM?* Resultó ser una pregunta sin objeto.

**Evidencia de consola (2026-09-02, nuestro workspace).** El diálogo *Create new Agent* ofrece siete tipos:

| Tipo | Naturaleza |
|---|---|
| Supervisor Agent | Gestionado por Databricks |
| Knowledge Assistant | Gestionado por Databricks |
| Genie Agent | Gestionado por Databricks |
| Information Extraction | Gestionado (`ai_extract`) |
| Document Parsing | Gestionado (`ai_parse_document`) |
| Text Classification | Gestionado (`ai_classify`) |
| **Code your own agent** | **Código propio — OSS libraries + Agent Framework** |

Bajo el filtro `Custom` queda **solo** "Code your own agent". No existe ningún tipo llamado "Custom LLM", y ninguno de los siete expone un selector de modelo base donde apuntar un serving endpoint arbitrario.

**Evidencia documental.** La página oficial de Custom LLM se titula literalmente *"Use Custom LLM to create an AI agent for text **(legacy)**"* y el feature figura en Beta con controles de administrador. La documentación no especifica si admite endpoints de modelos externos — la pregunta nunca tuvo respuesta publicada.

### Lo que sí se probó, y que conviene saber

Creamos un endpoint External Model real apuntando a Anthropic y lo consultamos end-to-end:

```
endpoint : asdk-14-anthropic-external-test   → DEPLOYMENT_READY
respuesta: model=claude-sonnet-4-6, content="EXTERNAL_MODEL_OK", 26 tokens
```

Así que **Model Serving sí sirve Anthropic vía External Models en nuestro workspace** — eso pasó de inferencia arquitectónica a hecho verificado. Reutiliza el secreto `uc13/anthropic_api_key` que ya teníamos, sin duplicarlo. Un detalle operativo útil: la resolución del secreto la hace el plano de serving, no la credencial del llamante — el token que creó el endpoint no tiene siquiera el scope `secrets`.

El endpoint quedó creado. No lo usa el pipeline VDR; existe como vía para cualquier consumidor futuro que exija un serving endpoint de Databricks.

### La conclusión que importa

**Agent Bricks no participa en lo que queremos construir.** La ruta viable es "Code your own agent" (OSS + Agent Framework), donde el código controla el cliente del modelo y nuestro gateway `llm_client.chat()` sirve sin adaptación alguna — no hay selector de modelo base que satisfacer.

Si algún día quisiéramos un Knowledge Assistant o un Supervisor Agent, ese agente usaría un modelo de Databricks. Eso sería una decisión de producto, **no una regresión causada por esta migración**.

### Un cambio de dirección de plataforma que conviene tener en el radar

Al verificar la documentación vigente apareció algo que actualiza el §2 de `platform-capabilities.md`, escrito antes:

> "Deploying a custom agent to its own Model Serving endpoint with `agents.deploy()` is a legacy path."

Databricks ahora recomienda **Databricks Apps** para desplegar agentes propios, en vez de un endpoint de Model Serving dedicado. La Supervisor API (Beta) figura como deprecada; Document Intelligence y Custom Agents pasaron a GA.

Implicación práctica: el "siguiente paso concreto" que T24 proponía —desplegar `KPIAgentEndpoint` a Model Serving para cerrar la duda de egress— apuntaría a un camino que la plataforma ya está retirando. **Antes de invertir ahí, conviene decidir si el destino es Databricks Apps.** No es urgente, porque hoy no desplegamos ningún agente; es una decisión a tomar antes de empezar, no después.

---

## 2. Por qué un framework de evaluación sí es viable

**El SDK de Anthropic no es un obstáculo, y esto ya no es teoría.**

MLflow Tracing es explícitamente agnóstico de proveedor, y `mlflow.genai.evaluate()` opera sobre **traces ya generados**, no sobre el proveedor que los produjo. Un trace con nuestros spans manuales es un insumo tan válido como uno producido por `mlflow.deployments`.

Lo que convirtió esto de lectura de documentación en hecho verificado fue un ejercicio de hoy. Al cerrar el último criterio de la validación de paridad, consultamos MLflow por API y sacamos:

```
spans de gateway en las 3 corridas de paridad : 266
llm.fallback_used                             : {'False': 266}
llm.backend                                   : {'anthropic': 266}
```

Es decir: **los traces del pipeline aterrizan en MLflow, con atributos por llamada, y son consultables programáticamente.** Ese es exactamente el sustrato sobre el que corre Agent Evaluation. La infraestructura de observabilidad existe y funciona.

La decisión de diseño de T11 —spans manuales en vez de `mlflow.anthropic.autolog()`— resultó afortunada: `autolog` solo está probado contra `anthropic` 0.55.0–0.107.1 y nosotros corremos 1.3.0. Si dependiéramos de `autolog`, hoy no tendríamos tracing. Con spans propios, no dependemos de que Anthropic y MLflow certifiquen una combinación de versiones.

---

## 3. Qué falta para implementar LLM judges

Aquí está el hallazgo concreto, y es acotado.

### El problema: nuestros traces son 100% metadata

Todo el pipeline tiene exactamente **tres** spans:

| Span | Dónde | Qué graba |
|---|---|---|
| `agent::{key}` | `pipeline.py:418` | nada — solo delimita |
| `agent::orchestrator` | `pipeline.py:548` | nada — solo delimita |
| `llm_client.chat` | `llm_client.py:570` | `llm.endpoint_alias`, `llm.backend`, `llm.fallback_used`, `llm.max_tokens`, `llm.prompt_tokens`, `llm.completion_tokens` |

**Ninguno llama a `set_inputs()` ni `set_outputs()`.** El prompt y la respuesta del modelo nunca entran al trace. Tampoco se declara `span_type`, así que los spans quedan como tipo genérico en vez de `CHAT_MODEL`/`LLM`.

Un detalle a corregir de paso: los docstrings de `pipeline.py` (líneas 30 y 403) hablan de *"each agent's `@mlflow.trace` spans"*. **Ese decorador no se usa en ninguna parte del repo.** Es documentación obsoleta que describe un mecanismo inexistente — y es justo el tipo de cosa que haría a alguien asumir que el contenido ya se está capturando.

### Por qué eso bloquea a los judges

La documentación de MLflow indica que los scorers integrados extraen inputs y outputs del trace, y que para traces que no los tienen en el span raíz, el scorer recurre a *tool calling* para pasarle la información del trace al juez. Pero ese mecanismo reparte lo que haya: **si ningún span del árbol contiene el contenido, al juez le llega metadata.** Un juez de relevancia no puede evaluar si la respuesta atiende la pregunta cuando no ve ni la pregunta ni la respuesta.

### Lo que se desbloquea, y a qué costo

Los judges integrados tienen requisitos distintos. Vale la pena verlos por costo de habilitación, porque no todos requieren el mismo esfuerzo:

**Grupo A — solo necesitan pregunta y/o respuesta. Cero dataset etiquetado.**

| Judge | Necesita |
|---|---|
| `RelevanceToQuery` | pregunta + respuesta |
| `Completeness` | respuesta |
| `Fluency` | respuesta |
| `Safety` | respuesta |
| `Summarization` | respuesta |

Estos cinco se habilitan **con un solo cambio**: grabar inputs/outputs en los spans. No hace falta ground truth, ni etiquetar nada, ni construir un dataset de evaluación. Es la relación esfuerzo/valor más alta del conjunto.

**Grupo B — necesitan ground truth.**

`Correctness` requiere `expected_facts`; `Equivalence` requiere la salida esperada. Implica construir y mantener un dataset etiquetado — trabajo real y recurrente, con expertos de dominio.

**Grupo C — los más valiosos para nuestro producto, y los que más falta hacen.**

`RetrievalGroundedness`, `RetrievalRelevance` y `RetrievalSufficiency` están marcados **"⚠️ Trace Required"**: necesitan que el trace contenga los documentos recuperados.

Estos merecen atención especial. Nuestro producto es diligencia de PE: **el riesgo de negocio real no es que la redacción sea mala, es que un hallazgo no esté respaldado por el data room.** `RetrievalGroundedness` mide exactamente eso. Pero hoy `retrieval.py` no emite ningún span, así que el contexto recuperado no está en el trace. Habilitar este grupo exige instrumentar la capa de retrieval, no solo el gateway.

### La decisión que hay que tomar antes de tocar código

Grabar inputs/outputs significa **meter contenido de data rooms de clientes en traces de MLflow**. Documentos de diligencia confidenciales.

Eso no es una mejora gratuita de observabilidad: es una decisión de gobierno de datos. Dónde se persiste, quién puede leer el experimento, cuánto tiempo se retiene, si aplica redacción o truncamiento, y qué dice el contrato con el cliente. **Esta conversación va antes que la implementación, no después.**

Es previsible que la respuesta no sea binaria. Hay posiciones intermedias razonables: grabar solo en el catálogo de evaluación y no en producción; truncar; redactar; o limitar la captura a las compañías de un conjunto de prueba designado.

### La buena noticia técnica

Por la decisión arquitectónica AD-001 de esta migración, **todas las llamadas a Claude pasan por un único punto**. Habilitar contenido en traces es una modificación de **una función** —`llm_client.chat()`— no de once call sites dispersos.

Antes de esta migración, el mismo cambio habría requerido once ediciones coordinadas, con la garantía práctica de que alguna quedaría fuera. Ese es exactamente el retorno que se buscaba al centralizar el gateway, y este es el primer caso donde se cobra.

---

## 4. Secuencia propuesta

1. **Decidir gobierno de datos** sobre contenido de clientes en traces. Bloquea todo lo demás. No es decisión de ingeniería.
2. **Instrumentar `llm_client.chat()`** con `set_inputs`/`set_outputs` y `span_type` — una función, conforme a lo decidido en el paso 1. Desbloquea los cinco judges del Grupo A.
3. **Spike de `mlflow.genai.evaluate()`** sobre un trace real del pipeline con un judge del Grupo A. Nunca se ha ejecutado; es el paso que convierte "viable según documentación" en "verificado". Acotado y barato.
4. **Instrumentar `retrieval.py`** si se quiere el Grupo C — que es donde está el valor de negocio real. Alcance mayor que el paso 2.
5. **Decidir destino de despliegue** (Databricks Apps vs. Model Serving) antes de invertir en desplegar cualquier agente, dado que `agents.deploy()` figura como ruta legacy.
6. **Corregir los docstrings de `pipeline.py`** que mencionan un `@mlflow.trace` inexistente. Trivial, pero induce a error sobre qué se está capturando.

Los pasos 1 y 5 son decisiones, no implementación. Los pasos 2 y 3 son pequeños y responden la pregunta de viabilidad de forma definitiva. El paso 4 es el proyecto de verdad.

---

## Anexo: qué está verificado y qué no

Distinguirlo importa, porque parte de esto se ha citado antes con más confianza de la que corresponde.

| Afirmación | Estado |
|---|---|
| Custom LLM no aparece en la consola de nuestro workspace | **Verificado** — inspección 2026-09-02 |
| Custom LLM figura *(legacy)* en documentación oficial | **Verificado** — título de la página |
| Model Serving sirve Anthropic vía External Model aquí | **Verificado** — endpoint creado y consultado |
| Los traces del pipeline aterrizan en MLflow y son consultables | **Verificado** — 266 spans extraídos por API |
| Ningún span graba inputs/outputs | **Verificado** — 3 `start_span` en el repo, ninguno los graba |
| `agents.deploy()` a Model Serving es ruta legacy | **Verificado** — cita textual de la documentación |
| Requisitos de cada judge integrado | **Verificado** — documentación de MLflow |
| `mlflow.genai.evaluate()` funciona sobre traces de este pipeline | **No verificado** — nunca ejecutado. Confianza alta por arquitectura, pero es lectura de documentación |
| Egress a Anthropic desde el plano de Model Serving | **No verificado** — T3 probó egress desde job serverless, que es otro plano de cómputo |

Las dos últimas líneas son las que quedan abiertas. Ninguna bloquea la decisión de gobierno de datos, que es el verdadero primer paso.

---

## Fuentes

- [Databricks — Use Custom LLM to create an AI agent for text (legacy)](https://docs.databricks.com/aws/en/agents/agent-bricks/custom-llm)
- [Databricks — Custom agent endpoints](https://developers.databricks.com/docs/agents/custom-agents)
- [Databricks — Scorers and LLM judges](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/scorers)
- [Databricks — Evaluate and monitor agents](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/)
- [MLflow — Predefined LLM Scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/predefined/)
- [MLflow — Tracing Anthropic (rango de versiones de autolog)](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/anthropic)

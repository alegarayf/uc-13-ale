# Context — decisiones del usuario (Discuss)

Capturado 2026-09-01. Estas son decisiones del usuario, no inferencias del agente.

| # | Gray area | Decisión | Implicación |
|---|---|---|---|
| D-1 | Semántica del fallback a Databricks Model Serving | **Automático por llamada.** Si la llamada al SDK de Anthropic falla, el mismo call reintenta contra el serving endpoint equivalente y continúa. | El gateway necesita un mapeo bidireccional de modelos, clasificación de errores retryables, y logging obligatorio de cada degradación. Riesgo aceptado: reintroduce silenciosamente el cap de 8K output de Haiku. Se mitiga con logging y una métrica de conteo de degradaciones. |
| D-2 | Alcance de la primera entrega | **Todos los call sites de chat + visión.** 10 de texto + 1 de visión. | Embeddings (`databricks-bge-large-en`) quedan explícitamente fuera — Anthropic no ofrece embeddings API. |
| D-3 | Fuente de la credencial | **Databricks Secret Scope**, siguiendo el patrón `get_secret()` ya usado para SharePoint. Nombre del scope parametrizable. | Crear el scope es un prerequisito operativo documentado, no una tarea de código. |
| D-4 | Egress de red desde jobs serverless hacia `api.anthropic.com` | **Desconocido — se verifica.** Smoke test como gate bloqueante antes de tocar código de producción. | La tarea 1 de Execute es un smoke test real en el job serverless. Si falla, el plan se detiene y escala a infraestructura (NCC / private egress). |

## Contexto adicional que motivó las preguntas

- El objetivo 2 del usuario ("preservar MLflow tracing, Agent Bricks, publicación de agentes, Mosaic AI Agent Evaluation") describe capacidades que **hoy no existen en el repo**: cero `mlflow.genai.evaluate`, cero `log_model`/`register_model`, cero autolog, y solo dos `mlflow.start_span()` manuales que no cubren ninguna llamada al modelo. Se reencuadró como *no bloquear la construcción futura* + *investigar viabilidad*, no como *preservar*.
- Agent Bricks es producto Databricks sobre modelos alojados en Databricks. Su compatibilidad con un cliente Anthropic externo es una incógnita real y se trata como spike de investigación con entregable documental, no como código comprometido.

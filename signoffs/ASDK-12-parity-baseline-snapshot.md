# ASDK-12 — Snapshot del baseline (capturado antes de las corridas post-migración)

**Fecha de captura**: 2026-09-02
**Por qué existe este documento separado**: las corridas post-migración escriben sobre las mismas filas de `companies_vdr_history` (mismo `id`), sobreescribiendo `results_location`/`total_tokens`/`updated_at`. Esta captura preserva el estado del baseline *antes* de que eso ocurra. El signoff final (`ASDK-12-parity.md`) compara contra estos valores, no contra lo que queda en la tabla después de correr.

Baseline designado por el usuario: los registros `62`, `63`, `64` — **no** el `32` que se identificó inicialmente (misma compañía GKF, corrida más reciente pero no la designada como referencia).

---

## `companies_vdr_history` — estado pre-corrida

| `id` | company_name | processing_status | completion_status | model_name | total_tokens | results_location | updated_at |
|---|---|---|---|---|---|---|---|
| 62 | GKF | done | success | databricks-claude-sonnet-4-6 | 426350 | `/Volumes/rallyday_partners_llc/default/vdr/gkf/20260826T192259Z/` | 2026-08-26T19:23:00.373Z |
| 63 | Clearsulting | done | success | databricks-claude-sonnet-4-6 | 470734 | `/Volumes/rallyday_partners_llc/default/vdr/clearsulting/20260826T192317Z/` | 2026-08-26T19:23:18.501Z |
| 64 | Elder Care | done | success | databricks-claude-sonnet-4-6 | 427881 | `/Volumes/rallyday_partners_llc/default/vdr/elder_care/20260826T192459Z/` | 2026-08-26T19:25:01.146Z |

## Tablas `uc13_preview.analysis.*` — conteo de filas por compañía (pre-corrida)

| Tabla | GKF | Clearsulting | Elder Care |
|---|---|---|---|
| `business_model` | 1 | 1 | 1 |
| `financial_trends` | 1 | 1 | 1 |
| `customer_quality` | 1 | 1 | 1 |
| `kpi` | 1 | 1 | 1 |
| `legal` | 1 | 1 | 1 |
| `quality_of_earnings` | 1 | 1 | 1 |
| `forecast` | 1 | 1 | 1 |
| `cross_analysis` | 1 | 1 | 1 |
| `diligence_report` | 0 | 0 | 3 |

**Lectura**: GKF y Clearsulting corrieron por la ruta CIM-scoped (Ruta 2, `run_orchestrator=False`) — `diligence_report` en 0 es el comportamiento esperado, no un gap. Elder Care tiene 3 filas históricas en `diligence_report`, de corridas full-room previas (no necesariamente de este `id=64` específico — la tabla acumula entre corridas).

## Artefactos en el volumen VDR (pre-corrida)

Los tres `results_location` contienen exactamente el mismo par de archivos — confirmando que las tres corridas baseline usaron la ruta CIM-scoped:

- `executive_summary.pdf`
- `rainmaker_opportunity_summary.html`

Ninguna contiene `full_report.docx` — consistente con CIM-scoped (ese artefacto solo lo produce la rama full-room).

---

## Criterio de comparación para el signoff final

Una corrida post-migración sobre la misma compañía se considera a la par del baseline si:

1. Los mismos 8 agentes de análisis (`business_model` … `cross_analysis`) ganan **una fila nueva** cada uno (no cero).
2. El nuevo `results_location` de la compañía contiene `executive_summary.pdf` + `rainmaker_opportunity_summary.html` — el mismo par, ni más ni menos.
3. `diligence_report` **no** gana una fila nueva para GKF/Clearsulting (seguirían por CIM-scoped); si Elder Care gana una fila, es señal de que corrió full-room esta vez — a verificar contra el `no_cim_mode` efectivo, no asumir automáticamente una regresión.
4. El manifiesto de agentes de la corrida (`agent_run_manifest_json`, cuando aplique) no muestra ningún agente en `FAILED` que el baseline no tuviera ya en ese estado.

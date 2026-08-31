# RB-DEFECT-T9-3 — runbook serverless steps closure

**Closed:** 2026-08-14  
**Defect:** Steps 3 and 5 lacked documented serverless deps, code-sync, and operator submit path.

**Resolution:**

- `eval/program/onboarding_runbook.md` — Step 3 and Step 5 each gain a **Cluster execution (serverless)** subsection referencing `.dev/onboarding_cluster_submit.py` (`bootstrap`, `harness-baseline`) and `.dev/agent-databricks-recipes.md`.
- Local `python -m eval.retrieval.*` blocks retained as **Reference shape (cluster CLI equivalent)**.
- Registry row `RB-DEFECT-T9-3` closed in `eval/program/registry.yaml`.

**Prior T9 cluster evidence:** Databricks runs `502286866957035` (bootstrap), `1086586115456516` (harness baseline).

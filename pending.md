
- ~~remove route a related files and others [route_chunks]~~ (done — kept retrieval_mode plumbing)



- 2/3 charter: .dev\orchestrator\uc13_orchestrator_milestone_charter.md
    - m3 - if gates or conditions are triggered 
    - + the experiment 
        - Lo que voy a agregar como experiment para la presetancion si el tiempo permite es uno con un llm generation mas agresivo y no tan determinista como está ahora; basciamente generando las secciones claves completamente del mismo bundle/source data. in_one_line, strengths, concerns, business_snapshot...
    - + change tl;dr name to executive summary 
    - + summarize or diagest bullets like mitigants w llms somehow 
    - 


- merge hectors repo (agents and auxs) 

- dataset / pre training
    - explore and evaluate datasets 
        - understand + try to extract minimal baseline from and for all companies and datasets 


- eval: 

    - re score all agents post m-re3
    - score fta (or full pipeline) on more companies
    - 



- What it is: A controlled experiment on Elder Care only — run the retrieval harness twice with vs_metadata_filters=False (production default) vs True (candidate M-PHV4 feature). Compare recall@10 per intent.

What it is NOT: Not a notebook cell, not --ablation-config, not Clearsulting.

What you do:

In a notebook cell on cluster (after Cell 1), run the harness twice using the pattern in eval/retrieval/README.md § ## R-02 manual A/B — flip VS_METADATA_FILTERS = False then True.
Baseline ref: baseline_299063e87806, company Elder Care, catalog uc13_ale.
Record both run_ids and per-intent recall@10 from each report.
Pass bar (Decision 14): no gate-eligible intent drops >5pp recall@10 vs Run A; aggregate recall@10 does not decrease.
Second reviewer (not you) signs off in the README table.
Effort: ~2 harness runs (much shorter than full pipeline). Can defer until after Gate 4 if you want — it’s supplementary for M-PHV4, not a charter exit gate.
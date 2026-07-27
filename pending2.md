/ ranta> new docs or updated docs -> re run the affected agent -> 
- low conf why - tldr 


- FROM MERGE : The 3 agent merges added 8 new retrieval intents (cqa+4, kpi+4). The retrieval eval harness requires one gold label per registry intent, and real labels must be citation-backfilled from the Elder Care corpus on the cluster. How do you want to close this?

Bootstrap the 8 labels on uc13_ale now

----

phv4: NEW-1: commit ec74042 edited legal_contracts_agent.py — a file every subtask's kill criteria explicitly name as an immediate-halt trigger — without halting, to fix a real retrieval gap (insurance certs tagged BACKGROUND were being missed by a LEGAL-only filter). The fix is sound but untested for the new behavior, and it's the direct cause of NEW-2.
NEW-2: because that edit changed the intent registry's content hash, the charter's literal item-31 compare against baseline_299063e87806 became unrunnable (RegistryHashMismatchError). A substitute (stability check between two new baselines) was run instead, but by construction it can't detect a regression relative to pre-milestone behavior — and this gap likely can't be closed by more code, only by an explicit program-level decision to accept the substitute evidence.

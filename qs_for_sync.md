
Decision worksheet: [.dev/uc13-retrieval-decision.md](.dev/uc13-retrieval-decision.md)

- how much time do I actually have? 
- how married are we to semantic retrieval? 
- Should keyword fallback remain silent, or become an explicit degraded mode in agent traces?
- what is priority (source_type_priority)


- [B]metadata filtering: index does sync but the query isnt called with metada filters 
    - today is a python filter after a global vector query not a constraint on the search itself
        - basically polluting the query - x agent asks for x_type chunks but SS finds NN across all chunks and docs and THEN it filters down. 
    
    [B]fixes to consider:
    - dynamic workstream filtering - filter by workstream at query time 
    - similarity is discarded today via ORDER BY priority_tier on the hydrate step -> explicit merge formula in python 
        - we're paying vdb costs for something closer to metadata + keyword routing
    - can consider reranking (cross encoder even on a small candidate set)


- compare routes before committing:
	- route to test thesis [A]
	- route to improve retrieval [B]
    - route to agents -> react agents [C] with access to SS which would close the loop with the vdb and retrieval
        - react agent connected to retrieval would justify the vdb much more cleanly than the current single shot design does
	
    
    - to consider: time


- meassure corpus (stats) + a/b one agent with route_chunks -> decide vs fate | react is a phase 2 bet unless we go interactive as prev discussed 
    - batch reports only vs future chat q&A / interactive ui


--- A: 
    Pre-compute structured MD (or JSON) per document or workstream at ingest:
    A LangGraph-style loop (extract → detect gaps → widen filters → trim → re-extract) is a cleaner expression of the same idea and **does not require embeddings**. Widening can mean: raise `tier_filter`, drop `file_name_filter`, add `section_header LIKE`, or fetch the next digest tranche.
    
    As is: Agent retrieval queries are **declarative routing specs** disguised as natural language: similarity is discarded, and agents rely on workstream tags, filename hints, and tier ordering.
    So retrieval is closer to “tier-biased routing”


### As is 

at chunk creation: chunks enriched via parsing with prefix: doc_title, section_header, page_id
embeddings: workstream, priority_tier -> joined from doc_relevance [In embeddings not chunks table]
semantic_search: vs + merge-rank + filters [my enchancement]
route_chunks: metadata routing
agent-time context building: dedups -> sorts CIM, tier 1, other before text -> truncates per chunk tier -> wraps as file x section y n {text}

### To try: 

    - contextual_prefix : at section level or per doc inserted in the children chunks to sitautate the chunk
        - should be cheap cost maybe haiku - 50-100 tokens
        - Options:
            - A: full doc for each chunk - if full doc, cached in the prompt 
            - B: section-scoped: group chunks by section - metadata + section_stex + chunk -> situating context
                - section == file, section_header, tab | the heading the parser already groups text under before it splits into chunks.




    - eval on retrieval intents from agent tools + queries + etc 
        - then gs p wrkstream w hand label chunk_id s and meassure 

    
    - rerank:
        - embed + bm25 + rerank 150 -> 20 k 


### To look into: 
    - chunks cited / used in extraction
    - extraction failures / null fields
    - queries used
    - chunks retrieved 
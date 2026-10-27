"""basic_rag: a from-scratch RAG pipeline over AMS company policies.

How the modules fit together:

Ingestion (run by ingest.py)
    parser.list_documents         find every .txt in ams-data/policies/
    parser.load_document          load each document's text
    -> chunker.chunk_text         split it into section-aware chunks
    -> embedder.embed_chunks      turn each chunk into a vector
    -> vector_store               recreate the collection, store chunks

Query (run by query.py)
    embedder.generate_embedding   turn the question into a vector
    -> vector_store.search        find the nearest chunks
    -> prompts.build_prompt       put question + chunks into a prompt
    -> generator.generate_answer  ask the LLM for the answer

Supporting modules
    config             every setting: URLs, model names, sizes, paths
    logger             coloured console output used by the scripts
    reranker           cross-encoder reranking (experiments only)
    compressor         context compression (experiments only)
    judge              LLM judge that grades answers (evals + experiments)
    character_chunker  simple fixed-size chunker (kept as an option)
"""

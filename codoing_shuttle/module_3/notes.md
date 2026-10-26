hybrid search -> dense retrieval and sparse
dense and sparse embeddings
sparse vector in each point (multiple vectors inside a same point)
dense vs sparse vs hybrid
multi vector retrieval
how to use router for different categorization
multi vector retrieval
contextual retrieval
query rewriting and query intelligence
multiquery retrieval
HYDE
reciprocal rank fusion
step back prompting
self query and structured filters
Query routing
differnt types of chunking

========================================================================================================

reranking (cross-encoder)
context selection (decompose -> dedup -> rerank -> threshold)
recalibration for no answer

1. Fixed-size chunking: Best for simple text documents where you want consistent chunk sizes, such as basic FAQs.

2. Recursive chunking: Best for general documents, blogs, and articles because it tries to preserve paragraphs and sentences. A good default for RAG.

3. Semantic chunking: Best for research papers and long articles where splitting based on changes in meaning can help preserve context.

4. Structure-aware chunking: Best for code documentation, legal documents, and Markdown files where headings, functions, or clauses should stay together.

5. Document-specific chunking: Best for structured data like tables, PDFs, or financial reports where the layout and relationships between data matter.

npx ccusage

In RAG, dense and sparse search help us retrieve relevant documents in different ways.

1. Dense search: Converts text into embeddings (vectors) and finds documents with similar meaning. For example, searching “How does Python free memory?” can retrieve a document about garbage collection, even if the exact words don't match.

2. Sparse search: Focuses on keyword matching. For example, searching for a specific error code like “ERR_CONNECTION_RESET” helps find documents containing that exact term. BM25 is a commonly used ranking algorithm.

3. Hybrid search: Combines both approaches. Dense search captures meaning, while sparse search finds exact terms. We can combine their results using RRF or another fusion method to improve retrieval.

# In production RAG, hybrid search is useful when both semantic understanding and exact keyword matching matter.

===============

- **Dense search:** Uses vector similarity, with HNSW commonly used to speed up nearest-neighbor search.
- **Sparse search:** Uses algorithms like BM25 to rank keyword matches.
- **RRF (Reciprocal Rank Fusion):** Combines the ranked results from both searches into one ranking.

So, hybrid retrieval = dense search + sparse search → RRF → final ranked results → LLM.

One thing to remember: BM25 is a ranking algorithm, not the only way to implement sparse search.

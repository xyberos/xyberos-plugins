# xyberos-knowledge

Document chunking, embedding, retrieval, and citations for Xyberos 2.x applications. The package
uses the core `EmbeddingModel` contract and defines a `VectorStore` protocol; it deliberately ships
no vector database backend.

## Install

```powershell
python -m pip install "xyberos-knowledge"
```

Provide an embedding-capable model and a vector store implementation at composition time. An
OpenAI-compatible embedding provider is available in `xyberos-openai-compatible`.

## Use

```python
from xyberos.ai import EmbeddingModel
from xyberos_knowledge import KnowledgeIndex, KnowledgeSettings, VectorStore

index = KnowledgeIndex(
    embedder,  # an EmbeddingModel with capabilities.embeddings=True
    vector_store,  # an application or adapter implementing VectorStore
    KnowledgeSettings(chunk_words=400, overlap_words=50),
)

await index.ingest(
    "handbook/access",
    "Access requests are approved by the service owner.",
    metadata={"department": "operations"},
)
hits = await index.search("Who approves access requests?", limit=3)
for hit in hits:
    print(hit.text, hit.citation.document_id, hit.citation.chunk_id)
```

`ingest` deterministically chunks text, embeds all chunks through `EmbeddingModel`, then replaces
that document's records through `VectorStore.replace_document`. `search` embeds the query and returns
passages with source identifiers and similarity scores. Metadata filters are exact equality filters.

## Boundaries

- The application owns vector-store construction, lifecycle, persistence, and provider credentials.
- Vector adapters should run `assert_vector_store_contract` from
  `xyberos_knowledge.testing` against their implementation.
- This package does not load files, assemble model prompts, generate answers, run agent loops, or
  authorize document access. Apply authorization filters before returning data to a caller.
- A `VectorStore` must return results in descending similarity order and replace each document as
  one logical operation. This package does not silently substitute an in-memory or no-op backend.

## Development

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

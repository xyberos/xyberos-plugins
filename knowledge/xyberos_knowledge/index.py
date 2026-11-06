"""Document chunking and provider-neutral embedding and retrieval."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from xyberos.ai import EmbeddingModel, EmbeddingRequest, EmbeddingResponse
from xyberos_knowledge.models import (
    Citation,
    IngestionReceipt,
    KnowledgeHit,
    VectorRecord,
)
from xyberos_knowledge.store import VectorStore


class KnowledgeError(RuntimeError):
    """An embedding provider or vector store violated the knowledge contract."""


@dataclass(frozen=True)
class KnowledgeSettings:
    """Deterministic word-based chunking defaults."""

    chunk_words: int = 400
    overlap_words: int = 50
    embedding_model: str | None = None
    timeout: float | None = None

    def __post_init__(self) -> None:
        if self.chunk_words < 1:
            raise ValueError("chunk_words must be at least one")
        if not 0 <= self.overlap_words < self.chunk_words:
            raise ValueError("overlap_words must be non-negative and smaller than chunk_words")
        if self.embedding_model is not None and not self.embedding_model.strip():
            raise ValueError("embedding_model must be non-empty when supplied")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")


class KnowledgeIndex:
    """Index and retrieve document passages using injected public contracts.

    This class does not construct prompts or call a chat model. Callers decide how retrieved
    passages are presented to a model and how each document is authorized.
    """

    def __init__(
        self,
        embedder: EmbeddingModel,
        vector_store: VectorStore,
        settings: KnowledgeSettings | None = None,
    ) -> None:
        if not embedder.capabilities.embeddings:
            raise ValueError("the embedding provider must declare embeddings=True")
        self._embedder = embedder
        self._vector_store = vector_store
        self.settings = KnowledgeSettings() if settings is None else settings

    async def ingest(
        self,
        document_id: str,
        text: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionReceipt:
        """Chunk, embed, and replace a document's indexed representation."""
        document_id = _require_nonempty_string(document_id, "document_id")
        chunks = chunk_text(
            text,
            chunk_words=self.settings.chunk_words,
            overlap_words=self.settings.overlap_words,
        )
        if not chunks:
            raise ValueError("document text must contain at least one non-whitespace character")
        response, vectors = await self._embed(chunks)
        attributes = {} if metadata is None else dict(metadata)
        records = tuple(
            VectorRecord(
                id=_chunk_id(document_id, index),
                document_id=document_id,
                text=chunk,
                vector=vector,
                metadata=attributes,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        )
        await self._vector_store.replace_document(document_id, records)
        return IngestionReceipt(document_id, len(records), response.model)

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[KnowledgeHit, ...]:
        """Embed a query and return source passages with stable citation identifiers."""
        query = _require_nonempty_string(query, "query")
        if limit < 1:
            raise ValueError("limit must be at least one")
        _, vectors = await self._embed((query,))
        matches = await self._vector_store.search(vectors[0], limit=limit, filters=filters)
        if len(matches) > limit:
            raise KnowledgeError(f"vector store returned {len(matches)} matches for limit {limit}")
        if any(
            matches[index].score < matches[index + 1].score for index in range(len(matches) - 1)
        ):
            raise KnowledgeError("vector store results are not ordered by descending similarity")
        return tuple(
            KnowledgeHit(
                text=match.text,
                citation=Citation(
                    document_id=match.document_id,
                    chunk_id=match.id,
                    score=match.score,
                ),
                metadata=match.metadata,
            )
            for match in matches
        )

    async def delete_document(self, document_id: str) -> bool:
        """Delete all indexed chunks for a document."""
        return await self._vector_store.delete_document(
            _require_nonempty_string(document_id, "document_id")
        )

    async def _embed(
        self, inputs: tuple[str, ...]
    ) -> tuple[EmbeddingResponse, tuple[tuple[float, ...], ...]]:
        response = await self._embedder.embed(
            EmbeddingRequest(
                inputs=inputs,
                model=self.settings.embedding_model,
                timeout=self.settings.timeout,
            )
        )
        response = _require_embedding_response(response)
        if len(response.embeddings) != len(inputs):
            raise KnowledgeError(
                f"embedding provider returned {len(response.embeddings)} vectors for "
                f"{len(inputs)} inputs"
            )
        vectors = tuple(tuple(float(value) for value in vector) for vector in response.embeddings)
        widths = {len(vector) for vector in vectors}
        if len(widths) != 1 or 0 in widths:
            raise KnowledgeError("embedding provider returned vectors with inconsistent dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise KnowledgeError("embedding provider returned a non-finite vector value")
        return response, vectors


def chunk_text(text: str, *, chunk_words: int = 400, overlap_words: int = 50) -> tuple[str, ...]:
    """Split text into deterministic word-count chunks with bounded overlap."""
    text = _require_string(text, "text")
    if chunk_words < 1:
        raise ValueError("chunk_words must be at least one")
    if not 0 <= overlap_words < chunk_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_words")
    words = text.split()
    if not words:
        return ()
    step = chunk_words - overlap_words
    chunks: list[str] = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + chunk_words]))
        if start + chunk_words >= len(words):
            break
    return tuple(chunks)


def _require_nonempty_string(value: object, label: str) -> str:
    normalized = _require_string(value, label).strip()
    if not normalized:
        raise ValueError(f"{label} must be a non-empty string")
    return normalized


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _require_embedding_response(value: object) -> EmbeddingResponse:
    if not isinstance(value, EmbeddingResponse):
        raise KnowledgeError(
            f"embedding provider returned {type(value).__name__}, not EmbeddingResponse"
        )
    return value


def _chunk_id(document_id: str, index: int) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"xyberos-knowledge:{document_id}")
    return str(uuid.uuid5(namespace, str(index)))

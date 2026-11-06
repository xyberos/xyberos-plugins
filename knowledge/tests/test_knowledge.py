from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

import pytest
from xyberos_knowledge import (
    KnowledgeIndex,
    KnowledgeSettings,
    VectorMatch,
    VectorRecord,
    chunk_text,
)
from xyberos_knowledge.index import KnowledgeError
from xyberos_knowledge.testing import assert_vector_store_contract

from xyberos.ai import EmbeddingRequest, EmbeddingResponse, ModelCapabilities


class FakeEmbedder:
    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(embeddings=True)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = tuple(_vector(text) for text in request.inputs)
        return EmbeddingResponse(model="fake", embeddings=vectors)


class NoEmbeddingModel(FakeEmbedder):
    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(embeddings=False)


class FakeVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, VectorRecord] = {}

    async def replace_document(self, document_id: str, records: Sequence[VectorRecord]) -> None:
        self.records = {
            key: value for key, value in self.records.items() if value.document_id != document_id
        }
        self.records.update({record.id: record for record in records})

    async def delete_document(self, document_id: str) -> bool:
        old_count = len(self.records)
        self.records = {
            key: value for key, value in self.records.items() if value.document_id != document_id
        }
        return len(self.records) != old_count

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[VectorMatch]:
        candidates = [
            record
            for record in self.records.values()
            if not filters
            or all(record.metadata.get(key) == value for key, value in filters.items())
        ]
        ranked = sorted(candidates, key=lambda record: _cosine(vector, record.vector), reverse=True)
        return tuple(
            VectorMatch(
                id=record.id,
                document_id=record.document_id,
                text=record.text,
                score=_cosine(vector, record.vector),
                metadata=record.metadata,
            )
            for record in ranked[:limit]
        )


def _vector(text: str) -> tuple[float, float]:
    lowered = text.lower()
    return (float(lowered.count("tea") + 1), float(lowered.count("coffee") + 1))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(first * second for first, second in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    return numerator / (left_norm * right_norm)


def test_chunking_is_deterministic_and_overlaps_words() -> None:
    assert chunk_text("one two three four five", chunk_words=3, overlap_words=1) == (
        "one two three",
        "three four five",
    )
    assert chunk_text("   ") == ()
    with pytest.raises(ValueError, match="smaller than"):
        chunk_text("one", chunk_words=2, overlap_words=2)


def test_ingestion_search_citations_replacement_and_delete() -> None:
    async def scenario() -> None:
        store = FakeVectorStore()
        index = KnowledgeIndex(
            FakeEmbedder(),
            store,
            KnowledgeSettings(chunk_words=5, overlap_words=1),
        )
        receipt = await index.ingest(
            "handbook/drinks",
            "tea is served here and coffee is served there",
            metadata={"team": "ops"},
        )
        assert receipt.chunks == 2
        hits = await index.search("tea", limit=1, filters={"team": "ops"})
        assert len(hits) == 1
        assert hits[0].citation.document_id == "handbook/drinks"
        assert hits[0].citation.chunk_id
        assert hits[0].metadata["team"] == "ops"

        updated = await index.ingest("handbook/drinks", "coffee only")
        assert updated.chunks == 1
        assert len(store.records) == 1
        assert await index.delete_document("handbook/drinks")
        assert not await index.delete_document("handbook/drinks")

    asyncio.run(scenario())


def test_store_contract_and_embedding_capability_are_enforced() -> None:
    async def scenario() -> None:
        checks = await assert_vector_store_contract(FakeVectorStore())
        assert len(checks) == 4
        with pytest.raises(ValueError, match="embeddings=True"):
            KnowledgeIndex(NoEmbeddingModel(), FakeVectorStore())

    asyncio.run(scenario())


def test_malformed_embedding_response_is_reported() -> None:
    class BadEmbedder(FakeEmbedder):
        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            return EmbeddingResponse(model="bad", embeddings=())

    async def scenario() -> None:
        index = KnowledgeIndex(BadEmbedder(), FakeVectorStore())
        with pytest.raises(KnowledgeError, match="vectors for"):
            await index.ingest("doc", "one two")

    asyncio.run(scenario())

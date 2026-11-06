"""A runnable, in-memory demonstration; production apps provide a persistent VectorStore."""

import asyncio
import math
from collections.abc import Mapping, Sequence

from xyberos_knowledge import KnowledgeIndex, VectorMatch, VectorRecord

from xyberos.ai import EmbeddingRequest, EmbeddingResponse, ModelCapabilities


class DemoEmbedder:
    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(embeddings=True)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = tuple(
            (float(text.lower().count("access")), float(text.lower().count("owner")) + 0.1)
            for text in request.inputs
        )
        return EmbeddingResponse(model="demo", embeddings=vectors)


class DemoVectorStore:
    def __init__(self) -> None:
        self._documents: dict[str, tuple[VectorRecord, ...]] = {}

    async def replace_document(self, document_id: str, records: Sequence[VectorRecord]) -> None:
        self._documents[document_id] = tuple(records)

    async def delete_document(self, document_id: str) -> bool:
        return self._documents.pop(document_id, None) is not None

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[VectorMatch]:
        ranked: list[tuple[float, VectorRecord]] = []
        for records in self._documents.values():
            for record in records:
                if filters and any(
                    record.metadata.get(key) != value for key, value in filters.items()
                ):
                    continue
                dot = sum(left * right for left, right in zip(vector, record.vector, strict=True))
                left_norm = math.sqrt(sum(value * value for value in vector))
                right_norm = math.sqrt(sum(value * value for value in record.vector))
                score = dot / (left_norm * right_norm)
                ranked.append((score, record))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return tuple(
            VectorMatch(
                id=record.id,
                document_id=record.document_id,
                text=record.text,
                score=score,
                metadata=record.metadata,
            )
            for score, record in ranked[:limit]
        )


async def main() -> None:
    index = KnowledgeIndex(DemoEmbedder(), DemoVectorStore())
    await index.ingest(
        "handbook/access",
        "Access requests are approved by the service owner.",
        metadata={"department": "operations"},
    )
    for hit in await index.search("Who approves access?", filters={"department": "operations"}):
        print(f"{hit.text} [{hit.citation.document_id}#{hit.citation.chunk_id}]")


if __name__ == "__main__":
    asyncio.run(main())

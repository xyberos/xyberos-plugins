"""Conformance checks for vector-store adapters."""

from __future__ import annotations

import uuid

from xyberos_knowledge.models import VectorRecord
from xyberos_knowledge.store import VectorStore


async def assert_vector_store_contract(store: VectorStore) -> tuple[str, ...]:
    """Check replacement, ranking, exact metadata filters, and deletion."""
    document_id = f"xyberos-vector-store-conformance-{uuid.uuid4()}"
    marker = str(uuid.uuid4())
    await store.replace_document(
        document_id,
        (
            VectorRecord("near", document_id, "near", (1.0, 0.0), {"kind": "kept", "run": marker}),
            VectorRecord("far", document_id, "far", (0.0, 1.0), {"kind": "ignored", "run": marker}),
        ),
    )
    initial = await store.search((1.0, 0.0), limit=2, filters={"run": marker})
    if tuple(match.id for match in initial) != ("near", "far"):
        raise AssertionError("search must return records in descending similarity order")
    checked = ["search ranks nearest records first"]

    filtered = await store.search((1.0, 0.0), limit=2, filters={"kind": "kept", "run": marker})
    if tuple(match.id for match in filtered) != ("near",):
        raise AssertionError("search must apply exact metadata filters")
    checked.append("search applies metadata filters")

    await store.replace_document(
        document_id,
        (
            VectorRecord(
                "replacement",
                document_id,
                "replacement",
                (0.0, 1.0),
                {"kind": "new", "run": marker},
            ),
        ),
    )
    replaced = await store.search((0.0, 1.0), limit=5, filters={"run": marker})
    if tuple(match.id for match in replaced) != ("replacement",):
        raise AssertionError("replace_document must remove stale records")
    checked.append("replace_document removes stale records")

    if not await store.delete_document(document_id):
        raise AssertionError("delete_document must report an existing document")
    if await store.delete_document(document_id):
        raise AssertionError("delete_document must report a missing document")
    checked.append("delete_document reports whether a document existed")
    return tuple(checked)

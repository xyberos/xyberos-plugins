"""Tests for loading the qdrant plugin into a Xyberos app."""

from __future__ import annotations

import pytest
from xyberos import create_app

from xyberos_qdrant import QdrantPlugin


def test_plugin_conforms_to_contract():
    plugin = QdrantPlugin(location=":memory:")
    assert plugin.name == "qdrant"
    assert callable(plugin.register) and callable(plugin.unregister)
    assert plugin.vector_store() is plugin.vector_store()


def test_plugin_registers_vector_store():
    pytest.importorskip("qdrant_client")
    app = create_app()
    app.load_plugin(QdrantPlugin(location=":memory:"))
    store = app.resolve("vector_store")
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
    assert store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=1)[0].payload["text"] == "alpha"
    app.unload_plugin("qdrant")

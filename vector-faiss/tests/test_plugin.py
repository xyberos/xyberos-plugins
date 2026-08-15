"""Tests for loading the faiss plugin into a Xyberos app."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos import create_app

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="faiss-cpu is not installed on this platform",
)

from xyberos_faiss import FaissPlugin  # noqa: E402


def test_plugin_conforms_to_contract():
    plugin = FaissPlugin()
    assert plugin.name == "faiss"
    assert callable(plugin.register) and callable(plugin.unregister)
    assert plugin.vector_store() is plugin.vector_store()


def test_plugin_registers_vector_store():
    app = create_app()
    app.load_plugin(FaissPlugin())
    store = app.resolve("vector_store")
    store.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
    assert store.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=1)[0].payload["text"] == "alpha"
    app.unload_plugin("faiss")

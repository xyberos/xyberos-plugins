"""Tests for loading the documents plugin into a Xyberos app."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from xyberos import create_app
from xyberos.exceptions.provider import ProviderError
from xyberos.knowledge import IngestingKnowledge
from xyberos.llm import HashEmbedder
from xyberos.vector import SqliteVectorStore

from xyberos_documents import DocumentsPlugin


def _app_with_ingesting_knowledge():
    knowledge = IngestingKnowledge(SqliteVectorStore(":memory:"), embedder=HashEmbedder())
    return create_app(knowledge=knowledge)


def test_plugin_conforms_to_contract():
    plugin = DocumentsPlugin()
    assert plugin.name == "documents"
    assert callable(plugin.register) and callable(plugin.unregister)
    assert {tool.name for tool in plugin.tools()} == {"ingest_document", "ingest_directory"}


def test_ingest_document(sample_txt):
    app = _app_with_ingesting_knowledge()
    app.load_plugin(DocumentsPlugin())
    result = app.tools.execute("ingest_document", None, path=str(sample_txt))
    assert result["documents"] == 1
    assert result["chunks"] == 1
    # Exact-match query against the ingested chunk returns the fact.
    knowledge = app.knowledge
    rendered = knowledge.query(SimpleNamespace(prompt="The quick brown fox jumps over the lazy dog."))
    assert "The quick brown fox jumps over the lazy dog." in rendered
    app.unload_plugin("documents")


def test_ingest_directory(sample_dir):
    app = _app_with_ingesting_knowledge()
    app.load_plugin(DocumentsPlugin())
    result = app.tools.execute(
        "ingest_directory", None, path=str(sample_dir), extensions=[".md"]
    )
    assert result["documents"] == 2  # a.md + nested/c.md
    assert result["chunks"] == 2
    app.unload_plugin("documents")


def test_ingest_directory_mixed_formats(sample_dir, sample_pdf):
    import importlib.util

    if not any(importlib.util.find_spec(lib) for lib in ("pypdf", "PyPDF2", "fitz")):
        pytest.skip("no PDF library available")
    # The sample_dir fixture is tmp_path, and sample_pdf writes into the same
    # tmp_path — so the walk covers every format automatically.
    app = _app_with_ingesting_knowledge()
    app.load_plugin(DocumentsPlugin())
    # a.md, b.txt, page.html, nested/c.md, sample.pdf
    result = app.tools.execute(
        "ingest_directory",
        None,
        path=str(sample_dir),
        extensions=[".md", ".txt", ".html", ".pdf"],
    )
    assert result["documents"] == 5
    assert result["chunks"] >= 5
    app.unload_plugin("documents")


def test_ingest_requires_ingesting_knowledge():
    app = create_app()  # default InMemoryKnowledge — no ingest()
    app.load_plugin(DocumentsPlugin())
    with pytest.raises(ProviderError, match="ingest"):
        app.tools.execute("ingest_document", None, path="anything.md")
    app.unload_plugin("documents")

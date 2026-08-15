"""Documents plugin (RFC-0019, M1) — filesystem + document loaders.

Registers two tools that feed an app's ``IngestingKnowledge``:

* ``ingest_document(path, chunk_size=512, loader=None)`` — load one file by
  extension and ingest it.
* ``ingest_directory(path, extensions=None, chunk_size=512, recursive=True)``
  — walk a folder, route each file to the right loader, and ingest everything.

Both tools require the registered ``knowledge`` provider to support ``ingest()``
(i.e. an ``IngestingKnowledge``); otherwise a clear ``ProviderError`` is raised.
"""

from __future__ import annotations

from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.exceptions.provider import ProviderError
from xyberos.tools import FunctionTool

from .registry import get_loader, load_directory, load_document


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class DocumentsPlugin(Plugin):
    """Registers the ``ingest_document`` and ``ingest_directory`` tools."""

    def __init__(self) -> None:
        self._kernel: Any = None
        self._tools: list[Tool] | None = None

    @property
    def name(self) -> str:
        return "documents"

    def tools(self) -> list[Tool]:
        if self._tools is None:
            self._tools = [
                FunctionTool(
                    "ingest_document",
                    self._ingest_document,
                    description=(
                        "Load a document (PDF/DOCX/HTML/CSV/XLSX/text) and ingest "
                        "it into the knowledge base as chunks."
                    ),
                ),
                FunctionTool(
                    "ingest_directory",
                    self._ingest_directory,
                    description=(
                        "Walk a directory and ingest every matching document "
                        "(per-extension loaders) into the knowledge base."
                    ),
                ),
            ]
        return self._tools

    def register(self, kernel: object) -> None:
        self._kernel = kernel
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)

    # -- tool bodies --------------------------------------------------------

    def _ingest_document(
        self,
        path: str,
        chunk_size: int = 512,
        loader: str | None = None,
    ) -> dict[str, Any]:
        knowledge = self._ingesting_knowledge()
        if loader and loader.lower() != "auto":
            documents = get_loader(loader).load(path)
        else:
            documents = load_document(path)
        total = sum(knowledge.ingest(doc.text, chunk_size=chunk_size) for doc in documents)
        return {"source": path, "documents": len(documents), "chunks": total}

    def _ingest_directory(
        self,
        path: str,
        extensions: list[str] | None = None,
        chunk_size: int = 512,
        recursive: bool = True,
    ) -> dict[str, Any]:
        knowledge = self._ingesting_knowledge()
        documents = load_directory(path, extensions=extensions, recursive=recursive)
        total = sum(knowledge.ingest(doc.text, chunk_size=chunk_size) for doc in documents)
        return {"source": path, "documents": len(documents), "chunks": total}

    def _ingesting_knowledge(self) -> Any:
        kernel = self._kernel
        if kernel is None:
            raise RuntimeError("documents plugin must be registered (load_plugin) before use")
        knowledge = kernel.resolve("knowledge")
        if not callable(getattr(knowledge, "ingest", None)):
            raise ProviderError(
                "the registered knowledge provider cannot ingest; register an "
                "IngestingKnowledge, e.g. "
                "create_app(knowledge=IngestingKnowledge(store, embedder=...))"
            )
        return knowledge


#: Auto-discovered by ``app.load_entry_points()``.
plugin = DocumentsPlugin()

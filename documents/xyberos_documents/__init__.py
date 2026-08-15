"""Filesystem + document loaders plugin (RFC-0019, M1).

Turns plain-text-only ingestion into real document ingestion. Each loader
returns text chunks that ``IngestingKnowledge.ingest`` consumes directly:

* :class:`FileLoader` and :class:`HtmlLoader` are **stdlib-only** (the
  zero-dependency core stays sacred).
* :class:`PdfLoader`, :class:`DocxLoader` and :class:`XlsxLoader` import their
  backend lazily and raise a clear ``ProviderError`` when it is missing
  (``pip install xyberos[documents]`` provides ``pypdf`` / ``python-docx`` /
  ``openpyxl``).
* :class:`CsvLoader` is stdlib-only (``csv``).

The :class:`~xyberos_documents.plugin.DocumentsPlugin` registers two tools —
``ingest_document`` and ``ingest_directory`` — that feed the app's
``IngestingKnowledge``.
"""

from .base import Document, Loader, chunk_text, chunk_documents
from .csv_loader import CsvLoader
from .docx_loader import DocxLoader
from .file_loader import FileLoader
from .html_loader import HtmlLoader
from .pdf_loader import PdfLoader
from .plugin import DocumentsPlugin
from .registry import get_loader, load_document, loader_for
from .xlsx_loader import XlsxLoader

__all__ = [
    "CsvLoader",
    "Document",
    "DocumentsPlugin",
    "DocxLoader",
    "FileLoader",
    "HtmlLoader",
    "Loader",
    "PdfLoader",
    "XlsxLoader",
    "chunk_documents",
    "chunk_text",
    "get_loader",
    "load_document",
    "loader_for",
]

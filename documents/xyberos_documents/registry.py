"""Route file extensions to loaders and auto-detect documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Document, Loader
from .csv_loader import CsvLoader
from .docx_loader import DocxLoader
from .file_loader import FileLoader
from .html_loader import HtmlLoader
from .pdf_loader import PdfLoader
from .xlsx_loader import XlsxLoader

#: Extension (lowercase, no dot) -> loader class.
LOADER_CLASSES: dict[str, type] = {
    ".html": HtmlLoader,
    ".htm": HtmlLoader,
    ".pdf": PdfLoader,
    ".docx": DocxLoader,
    ".csv": CsvLoader,
    ".xlsx": XlsxLoader,
    ".xlsm": XlsxLoader,
}

#: Named loaders usable from the ``ingest_document`` tool's ``loader`` argument.
NAMED_LOADERS: dict[str, type] = {
    "auto": None,  # resolved by extension
    "text": FileLoader,
    "html": HtmlLoader,
    "pdf": PdfLoader,
    "docx": DocxLoader,
    "csv": CsvLoader,
    "xlsx": XlsxLoader,
}


def loader_for(extension: str, *, chunk_size: int | None = None) -> Loader:
    """Return the loader for ``extension`` (defaults to the text ``FileLoader``)."""
    ext = str(extension).lower()
    if ext in LOADER_CLASSES:
        return LOADER_CLASSES[ext](chunk_size=chunk_size)  # type: ignore[call-arg]
    return FileLoader(extensions=[ext], chunk_size=chunk_size)


def get_loader(name: str, *, chunk_size: int | None = None) -> Loader:
    """Return a loader by its named key (``auto``, ``text``, ``html``, ...)."""
    key = str(name).lower()
    if key not in NAMED_LOADERS:
        raise ValueError(f"unknown loader '{name}' (expected one of {sorted(NAMED_LOADERS)})")
    cls = NAMED_LOADERS[key]
    if cls is None:  # auto
        return loader_for("*", chunk_size=chunk_size)
    return cls(chunk_size=chunk_size)  # type: ignore[call-arg]


def load_document(path: str, *, chunk_size: int | None = None) -> list[Document]:
    """Load ``path`` using the loader that matches its extension."""
    extension = Path(path).suffix.lower()
    if extension in LOADER_CLASSES:
        return LOADER_CLASSES[extension](chunk_size=chunk_size).load(path)  # type: ignore[call-arg]
    return FileLoader(chunk_size=chunk_size).load(path)


def load_directory(
    path: str,
    *,
    extensions: list[str] | None = None,
    recursive: bool = True,
    chunk_size: int | None = None,
) -> list[Document]:
    """Load every matching file under ``path`` with per-extension loaders.

    Unlike :class:`FileLoader` (which reads files as plain text), this routes
    each file to the loader that understands its format — so a folder mixing
    PDF/DOCX/CSV ingests correctly.
    """
    root = Path(path)
    if not root.is_dir():
        raise NotADirectoryError(path)
    wanted = {str(e).lower().lstrip(".") for e in (extensions or ())}
    files: list[Path] = []
    iterator = root.rglob("*") if recursive else root.glob("*")
    for candidate in sorted(iterator):
        if not candidate.is_file():
            continue
        if any(part.startswith(".") for part in candidate.parts):
            continue
        if wanted and candidate.suffix.lower().lstrip(".") not in wanted:
            continue
        files.append(candidate)
    documents: list[Document] = []
    for file_path in files:
        documents.extend(load_document(str(file_path), chunk_size=chunk_size))
    return documents

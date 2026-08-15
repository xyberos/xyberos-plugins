"""PDF loader — lazy ``pypdf`` / ``PyPDF2`` / ``pymupdf`` import.

PDF extraction needs a third-party package; it is imported lazily on first use
and a clear :class:`~xyberos.exceptions.provider.ProviderError` is raised when
none is installed. ``pip install xyberos[documents]`` provides ``pypdf``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .base import Document, chunk_documents


def _extract_pdf(path: Path) -> tuple[str, int]:
    """Return ``(text, page_count)`` using whichever PDF library is available."""
    try:
        import pypdf  # preferred

        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages), len(reader.pages)
    except ImportError:
        pass

    try:
        import PyPDF2  # legacy name for the same library

        reader = PyPDF2.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages), len(reader.pages)
    except ImportError:
        pass

    try:
        import fitz  # PyMuPDF

        document = fitz.open(str(path))
        try:
            return "\n\n".join(page.get_text() for page in document), document.page_count
        finally:
            document.close()
    except ImportError:
        raise ProviderError(
            "the 'pypdf' package (or PyPDF2 / PyMuPDF) is required to load PDFs; "
            "install it with 'pip install xyberos[documents]'"
        ) from None


class PdfLoader:
    """Loads a PDF file as text (one page joined with a blank line)."""

    def __init__(self, chunk_size: int | None = None) -> None:
        self._chunk_size = chunk_size

    def load(self, path: str) -> list[Document]:
        path_obj = Path(path)
        if not path_obj.is_file():
            raise FileNotFoundError(path)
        text, page_count = _extract_pdf(path_obj)
        document = Document(
            source=str(path_obj),
            text=text,
            metadata={"pages": page_count, "extension": ".pdf"},
        )
        return chunk_documents([document], self._chunk_size)

"""Tests for the lazy PdfLoader (skips when no PDF library is installed)."""

from __future__ import annotations

import importlib.util

import pytest

from xyberos_documents import PdfLoader

PDF_LIBS = ("pypdf", "PyPDF2", "fitz")


def test_extracts_text(sample_pdf):
    if not any(importlib.util.find_spec(lib) for lib in PDF_LIBS):
        pytest.skip("no pypdf / PyPDF2 / PyMuPDF available")
    docs = PdfLoader().load(str(sample_pdf))
    assert len(docs) == 1
    assert "Hello Xyberos PDF" in docs[0].text
    assert docs[0].metadata["pages"] == 1

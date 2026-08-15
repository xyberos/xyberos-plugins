"""Tests for extension -> loader routing."""

from __future__ import annotations

import importlib.util

import pytest

from xyberos_documents import (
    CsvLoader,
    DocxLoader,
    FileLoader,
    HtmlLoader,
    PdfLoader,
    XlsxLoader,
    get_loader,
    load_document,
    loader_for,
)


def test_loader_for_known_extensions():
    assert isinstance(loader_for(".html"), HtmlLoader)
    assert isinstance(loader_for(".htm"), HtmlLoader)
    assert isinstance(loader_for(".pdf"), PdfLoader)
    assert isinstance(loader_for(".docx"), DocxLoader)
    assert isinstance(loader_for(".csv"), CsvLoader)
    assert isinstance(loader_for(".xlsx"), XlsxLoader)


def test_loader_for_defaults_to_text():
    loader = loader_for(".md")
    assert isinstance(loader, FileLoader)
    assert "md" in loader.extensions


def test_get_loader_by_name():
    assert isinstance(get_loader("html"), HtmlLoader)
    assert isinstance(get_loader("pdf"), PdfLoader)
    assert isinstance(get_loader("text"), FileLoader)


def test_get_loader_unknown_raises():
    with pytest.raises(ValueError, match="unknown loader"):
        get_loader("bogus")


def test_load_document_auto_detect(tmp_path, sample_pdf, sample_docx):
    md = tmp_path / "note.md"
    md.write_text("Markdown text.", encoding="utf-8")
    assert load_document(str(md))[0].text == "Markdown text."
    if any(importlib.util.find_spec(lib) for lib in ("pypdf", "PyPDF2", "fitz")):
        assert "Hello Xyberos PDF" in load_document(str(sample_pdf))[0].text
    assert load_document(str(sample_docx))[0].metadata["extension"] == ".docx"

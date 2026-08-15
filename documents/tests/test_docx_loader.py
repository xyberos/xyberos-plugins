"""Tests for the lazy DocxLoader (skips when python-docx is missing)."""

from __future__ import annotations

from xyberos_documents import DocxLoader


def test_extracts_paragraphs_and_tables(sample_docx):
    docs = DocxLoader().load(str(sample_docx))
    assert len(docs) == 1
    text = docs[0].text
    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "Alpha" in text
    assert "Name | Value" in text
    assert docs[0].metadata["tables"] == 1

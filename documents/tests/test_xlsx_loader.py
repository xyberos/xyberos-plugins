"""Tests for the lazy XlsxLoader (skips when openpyxl is missing)."""

from __future__ import annotations

from xyberos_documents import XlsxLoader


def test_parses_cells(sample_xlsx):
    docs = XlsxLoader().load(str(sample_xlsx))
    assert len(docs) == 1
    text = docs[0].text
    assert "# Sheet1" in text
    assert "name | value" in text
    assert "alpha | 1" in text
    assert "beta | 2" in text
    assert docs[0].metadata["sheets"] == ["Sheet1"]
    assert docs[0].metadata["row_count"] == 3

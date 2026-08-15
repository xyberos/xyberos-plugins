"""Tests for the stdlib CsvLoader."""

from __future__ import annotations

from xyberos_documents import CsvLoader

_CSV = "name,value\nalpha,1\nbeta,2\n"


def test_parses_rows(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(_CSV, encoding="utf-8")
    docs = CsvLoader().load(str(path))
    assert len(docs) == 1
    text = docs[0].text
    assert "name | value" in text
    assert "alpha | 1" in text
    assert "beta | 2" in text
    assert docs[0].metadata["columns"] == ["name", "value"]
    assert docs[0].metadata["row_count"] == 3

"""Tests for the stdlib FileLoader."""

from __future__ import annotations

import pytest

from xyberos_documents import FileLoader


def test_load_single_file(sample_txt):
    docs = FileLoader().load(str(sample_txt))
    assert len(docs) == 1
    assert "quick brown fox" in docs[0].text
    assert docs[0].metadata["extension"] == ".md"


def test_load_directory_recursive_with_extension_filter(sample_dir):
    docs = FileLoader(extensions=[".md", ".txt"]).load(str(sample_dir))
    sources = {d.source for d in docs}
    assert len(sources) == 3  # a.md, b.txt, nested/c.md
    assert not any("skip.md" in s for s in sources)  # hidden dir skipped


def test_load_directory_non_recursive(sample_dir):
    docs = FileLoader(extensions=[".md"], recursive=False).load(str(sample_dir))
    assert {d.source for d in docs} == {str(sample_dir / "a.md")}


def test_chunking(sample_txt):
    long_text = "\n\n".join(f"Paragraph number {i} with enough words to split." for i in range(20))
    sample_txt.write_text(long_text, encoding="utf-8")
    docs = FileLoader(chunk_size=50).load(str(sample_txt))
    assert len(docs) > 1
    assert all(len(d.text) <= 50 for d in docs)
    assert docs[0].metadata["chunk"] == 0


def test_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileLoader().load(str(tmp_path / "nope.txt"))

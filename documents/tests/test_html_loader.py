"""Tests for the stdlib HtmlLoader."""

from __future__ import annotations

from xyberos_documents import HtmlLoader

_HTML = """
<html>
  <head><title>Test Page</title></head>
  <body>
    <h1>Heading</h1>
    <p>Some <b>bold</b> text.</p>
    <script>var secret = "no";</script>
    <style>.hidden { color: red; }</style>
    <p>After script.</p>
  </body>
</html>
"""


def test_strips_tags_and_script(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(_HTML, encoding="utf-8")
    docs = HtmlLoader().load(str(path))
    assert len(docs) == 1
    text = docs[0].text
    assert "Some bold text." in text
    assert "After script." in text
    assert "Heading" in text
    assert "var secret" not in text
    assert ".hidden" not in text
    assert docs[0].metadata["title"] == "Test Page"


def test_chunking(tmp_path):
    body = "".join(f"<p>Sentence {i} here.</p>" for i in range(30))
    path = tmp_path / "big.html"
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    docs = HtmlLoader(chunk_size=60).load(str(path))
    assert len(docs) > 1

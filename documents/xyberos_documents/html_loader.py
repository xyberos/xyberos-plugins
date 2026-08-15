"""HTML loader — strip tags to text using only the standard library.

Uses ``html.parser.HTMLParser`` (plus ``html.unescape``), so it needs no
BeautifulSoup. Extracts the ``<title>`` into document metadata and ignores
``<script>`` / ``<style>`` content.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .base import Document, chunk_documents

_SKIP_TAGS = {"script", "style"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "section", "article"} | {
    f"h{level}" for level in range(1, 7)
}


class _TextExtractor(HTMLParser):
    """Collects text while dropping markup and script/style bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self.title: str | None = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS and not self._skip_depth:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS and not self._skip_depth:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data
        else:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"[ \t]+", " ", raw)
        # note: newlines collapsed below in finalize()


class HtmlLoader:
    """Loads an HTML file as readable text with a ``title`` metadata field."""

    def __init__(self, chunk_size: int | None = None) -> None:
        self._chunk_size = chunk_size

    def load(self, path: str) -> list[Document]:
        raw = Path(path).read_bytes()
        for encoding in ("utf-8", "latin-1"):
            try:
                html = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:  # pragma: no cover - latin-1 never fails
            html = raw.decode("latin-1", errors="replace")

        extractor = _TextExtractor()
        extractor.feed(html)
        extractor.close()
        text = _collapse_whitespace(extractor.text())
        document = Document(
            source=str(path),
            text=text,
            metadata={"title": extractor.title.strip() if extractor.title else None},
        )
        return chunk_documents([document], self._chunk_size)


def _collapse_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

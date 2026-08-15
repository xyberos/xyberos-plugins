"""CSV loader — stdlib-only (``csv``).

Each row becomes one line with columns joined by ``" | "``; the first row is
kept as the header line and also recorded in metadata.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .base import Document, chunk_documents


class CsvLoader:
    """Loads a CSV file as text (one line per row, columns joined)."""

    def __init__(self, chunk_size: int | None = None, *, delimiter: str = ",") -> None:
        self._chunk_size = chunk_size
        self._delimiter = delimiter

    def load(self, path: str) -> list[Document]:
        path_obj = Path(path)
        if not path_obj.is_file():
            raise FileNotFoundError(path)
        with path_obj.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter=self._delimiter))
        columns = rows[0] if rows else []
        lines = [" | ".join(cell.strip() for cell in row) for row in rows]
        document = Document(
            source=str(path_obj),
            text="\n".join(lines),
            metadata={
                "columns": columns,
                "row_count": len(rows),
                "extension": ".csv",
            },
        )
        return chunk_documents([document], self._chunk_size)

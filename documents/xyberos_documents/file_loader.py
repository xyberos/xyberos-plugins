"""Filesystem loader — walk directories, filter by extension, yield chunks.

Stdlib-only (``pathlib``). Reading a directory recursively produces one
:class:`Document` per matching file; ``chunk_size`` expands each into chunked
documents suitable for ``IngestingKnowledge.ingest``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .base import Document, chunk_documents


class FileLoader:
    """Loads plain-text files (and directories of them) from the filesystem."""

    def __init__(
        self,
        extensions: Iterable[str] | None = None,
        *,
        recursive: bool = True,
        chunk_size: int | None = None,
    ) -> None:
        self._extensions = {str(e).lower().lstrip(".") for e in (extensions or ())}
        self._recursive = recursive
        self._chunk_size = chunk_size

    @property
    def extensions(self) -> set[str]:
        return self._extensions

    def load(self, path: str) -> list[Document]:
        """Load a single file, or every matching file under a directory."""
        path_obj = Path(path)
        if path_obj.is_dir():
            documents = [self._load_file(f) for f in self._iter_files(path_obj)]
        elif path_obj.is_file():
            documents = [self._load_file(path_obj)]
        else:
            raise FileNotFoundError(path)
        return chunk_documents([d for d in documents if d is not None], self._chunk_size)

    # -- internals ----------------------------------------------------------

    def _iter_files(self, root: Path) -> list[Path]:
        iterator = root.rglob("*") if self._recursive else root.glob("*")
        files: list[Path] = []
        for path in sorted(iterator):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue  # skip hidden dirs/files
            if self._extensions and path.suffix.lower().lstrip(".") not in self._extensions:
                continue
            files.append(path)
        return files

    def _load_file(self, path: Path) -> Document | None:
        text = _read_text(path)
        if text is None:
            return None
        return Document(
            source=str(path),
            text=text,
            metadata={"path": str(path), "extension": path.suffix.lower()},
        )


def _read_text(path: Path) -> str | None:
    """Best-effort UTF-8 read with a latin-1 fallback."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except (OSError, ValueError):
            return None
    return None

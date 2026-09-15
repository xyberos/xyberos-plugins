"""PEP 561 regression guard for the ``py.typed`` marker.

``xyberos_documents`` is fully inline-annotated, so it must declare itself as a
typed package. Without the marker, consumers in strict mode get:

    from xyberos_documents import DocumentsPlugin
    # reportMissingTypeStubs: Stub file not found for "xyberos_documents"

The marker has to sit *inside* the package directory (next to ``__init__.py``);
a copy at the repo root would not be visible to type checkers or consumers.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_type_hints

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PACKAGE_ROOT / "xyberos_documents"
MARKER = PACKAGE_DIR / "py.typed"


def test_py_typed_marker_exists():
    assert MARKER.is_file(), (
        "xyberos_documents/py.typed is missing; strict-mode Pylance will report "
        "reportMissingTypeStubs for 'from xyberos_documents import DocumentsPlugin'"
    )


def test_marker_is_visible_beside_the_package():
    """PEP 561 requires the marker inside the package, not beside it.

    Deliberately checks importlib-resolvable location rather than asserting a
    specific packaging config line: setuptools ships ``py.typed`` by default, so
    a config assertion would test an implementation detail, not the outcome.
    """
    from importlib.resources import files

    assert files("xyberos_documents").joinpath("py.typed").is_file()


def test_public_api_is_annotated():
    """A typed package must expose annotated signatures for its public API.

    Uses ``get_type_hints`` rather than ``__annotations__`` because the modules
    use ``from __future__ import annotations`` (PEP 563), so raw annotations are
    strings.
    """
    from xyberos_documents import DocumentsPlugin, chunk_text, load_document

    assert get_type_hints(DocumentsPlugin.__init__)["return"] is type(None)
    assert get_type_hints(chunk_text)["return"] == list[str]
    assert "chunk_size" in get_type_hints(load_document)

"""Example (M4): use FAISS as the app's VectorStore (local, no server).

Run from this folder (requires ``pip install faiss-cpu``):

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_faiss import FaissPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(FaissPlugin())
    store = app.resolve("vector_store")

    store.upsert("examples", "doc-1", [1.0, 0.0, 0.0, 0.0], {"text": "north"})
    store.upsert("examples", "doc-2", [0.0, 1.0, 0.0, 0.0], {"text": "east"})
    store.upsert("examples", "doc-3", [0.0, 0.0, 1.0, 0.0], {"text": "south"})

    for hit in store.query("examples", [1.0, 0.1, 0.0, 0.0], top_k=2):
        print(f"  {hit.id:>8}  score={hit.score:.3f}  payload={hit.payload}")

    app.unload_plugin("faiss")


if __name__ == "__main__":
    main()

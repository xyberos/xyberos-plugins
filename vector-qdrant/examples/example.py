"""Example (M4): use Qdrant as the app's VectorStore (in-memory local mode).

Run from this folder:

    python examples/example.py

For hosted Qdrant, set QDRANT_URL and QDRANT_API_KEY (or pass url=/api_key=
to QdrantPlugin). The example uses Qdrant's local in-memory mode so it runs
with zero infrastructure.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_qdrant import QdrantPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(QdrantPlugin(location=":memory:"))
    store = app.resolve("vector_store")

    store.upsert("examples", "doc-1", [1.0, 0.0, 0.0, 0.0], {"text": "north"})
    store.upsert("examples", "doc-2", [0.0, 1.0, 0.0, 0.0], {"text": "east"})
    store.upsert("examples", "doc-3", [0.0, 0.0, 1.0, 0.0], {"text": "south"})

    for hit in store.query("examples", [1.0, 0.1, 0.0, 0.0], top_k=2):
        print(f"  {hit.id:>8}  score={hit.score:.3f}  payload={hit.payload}")

    app.unload_plugin("qdrant")


if __name__ == "__main__":
    main()

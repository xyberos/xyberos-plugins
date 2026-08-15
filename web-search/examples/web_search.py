"""Example (M5): search the web through one WebSearch contract.

Set the provider's API key env var first, e.g.:

    export TAVILY_API_KEY=...
    python examples/web_search.py

Swap providers with --provider serper|brave|exa|firecrawl (and the matching
*_API_KEY env var).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_web_search import WebSearchPlugin


def main() -> None:
    parser = argparse.ArgumentParser(description="Web search via xyberos")
    parser.add_argument("--query", default="what is xyberos?")
    parser.add_argument("--provider", default="tavily")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    app = create_app()
    app.load_plugin(WebSearchPlugin(provider=args.provider))
    results = app.tools.execute("web_search", None, query=args.query, top_k=args.top_k)

    for index, result in enumerate(results, start=1):
        print(f"{index}. {result['title']}\n   {result['url']}\n   {result['snippet']}")

    app.unload_plugin("web_search")


if __name__ == "__main__":
    main()

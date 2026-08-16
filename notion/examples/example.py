"""Example (M7): Notion tools via the xyberos plugin. Requires NOTION_TOKEN.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_notion import NotionPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(NotionPlugin())

    results = app.tools.execute("notion_search", None, query="roadmap")
    print("search results:", results[:5])

    # Replace DATABASE_ID with a real Notion database id.
    # created = app.tools.execute("notion_create_page", None, database_id="DATABASE_ID", title="New page")
    # print("created:", created)

    app.unload_plugin("notion")


if __name__ == "__main__":
    main()

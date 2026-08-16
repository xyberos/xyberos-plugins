"""Example (M7): Linear tools via the xyberos plugin. Requires LINEAR_API_KEY.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_linear import LinearPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(LinearPlugin())

    issues = app.tools.execute("linear_search_issues", None, first=5)
    for issue in issues:
        print(f"  {issue['identifier']}: {issue['title']}")

    app.unload_plugin("linear")


if __name__ == "__main__":
    main()

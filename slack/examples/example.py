"""Example (M7): Slack tools via the xyberos plugin. Requires SLACK_TOKEN.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_slack import SlackPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(SlackPlugin())

    channels = app.tools.execute("slack_list_channels", None)
    print("channels:", [c["name"] for c in channels])
    if channels:
        result = app.tools.execute("slack_post_message", None, channel=channels[0]["name"], text="hello from xyberos")
        print("posted:", result)

    app.unload_plugin("slack")


if __name__ == "__main__":
    main()

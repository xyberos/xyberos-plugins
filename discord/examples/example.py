"""Example (M7): Discord tools via the xyberos plugin. Requires DISCORD_TOKEN.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_discord import DiscordPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(DiscordPlugin())

    # Replace with a real channel id from your Discord server.
    channel_id = "CHANNEL_ID"
    channel = app.tools.execute("discord_get_channel", None, channel_id=channel_id)
    print("channel:", channel)
    if channel.get("name"):
        sent = app.tools.execute("discord_send_message", None, channel_id=channel_id, content="hello from xyberos")
        print("sent:", sent)

    app.unload_plugin("discord")


if __name__ == "__main__":
    main()

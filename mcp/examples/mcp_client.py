"""Example (M3): connect the MCP client to a real local server, list + call a tool.

Launches the bundled ``demo_mcp_server.py`` as a stdio MCP server, then loads
the MCP plugin and calls one of its tools. Run from this folder:

    python examples/mcp_client.py

For remote servers, set MCP_SERVERS (a JSON path or inline JSON) or pass
``McpPlugin("examples/servers.json")``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_mcp import McpPlugin


def main() -> None:
    server_script = Path(__file__).parent / "demo_mcp_server.py"
    servers = {"demo": {"command": [sys.executable, str(server_script)]}}

    app = create_app()
    app.load_plugin(McpPlugin(servers))

    print("server tools:", [name for name in app.tools.names if name.startswith("demo_")])
    print("echo ->", app.tools.execute("demo_echo", None, text="hello mcp", repeat=2))
    print("add  ->", app.tools.execute("demo_add", None, a=20, b=22))

    app.unload_plugin("mcp")


if __name__ == "__main__":
    main()

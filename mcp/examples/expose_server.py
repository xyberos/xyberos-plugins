"""Expose a Xyberos app's tools as an MCP server (stdio by default).

Run it directly to smoke-test::

    pip install "xyberos-mcp[mcp]"   # the official MCP SDK
    python examples/expose_server.py # blocks, serving over stdio

Then point an MCP client (Claude Desktop, VS Code Copilot, ...) at this
command. With the web-search plugin installed you can expose the real
``web_search`` tool instead of the placeholder below.
"""

from xyberos import create_app
from xyberos.tools import FunctionTool
from xyberos_mcp import expose


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def web_search(query: str, top_k: int = 5) -> str:
    """Search placeholder - install xyberos-web-search for the real tool."""
    return f"query={query!r} top_k={top_k}"


app = create_app()
app.tools.register(FunctionTool("add", add, description="Add two numbers"))
app.tools.register(FunctionTool("web_search", web_search, description="Search the web"))

# Optional: load the real, free web-search plugin (registers ``web_search``)
# from xyberos_web_search import WebSearchPlugin
# app.load_plugin(WebSearchPlugin())   # default provider: duckduckgo (no API key)

# Expose every tool over stdio:          python examples/expose_server.py
# Expose only a subset:                  expose(app, tools=["add"])
# Run over streamable HTTP:              expose(app, transport="streamable-http")
expose(app)

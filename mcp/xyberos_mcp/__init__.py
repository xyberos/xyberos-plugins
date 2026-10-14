"""Serve an application's registered tools to an MCP client.

The other half of the seam ``xyberos.mcp`` opens. The core package consumes another server's tools;
this package offers an application's tools *to* a client, so one name answers one question and the
client is not here — nor is a stdio transport, which stays withheld until the project owner
approves one.

    from xyberos import App
    from xyberos.ai import Tool, ToolSpec
    from xyberos_mcp import expose

    app = App()
    expose(app, [Tool(spec=ToolSpec(name="search", ...), handler=search)])

``expose`` registers a ``POST`` route (``/mcp`` unless another path is named) that speaks JSON-RPC
2.0 over the core HTTP adapter, and returns the :class:`McpServer` that answers on it. What the
route does not do is authenticate the caller: the framework ships no identity or authorization model
([ADR 0014]), so verification belongs in front of the route, as adapter middleware or at the edge.

[ADR 0014]: https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md
"""

from xyberos_mcp.protocol import SUPPORTED_PROTOCOL_VERSION
from xyberos_mcp.server import SERVER_NAME, McpServer, expose

__all__ = ["SERVER_NAME", "SUPPORTED_PROTOCOL_VERSION", "McpServer", "expose"]

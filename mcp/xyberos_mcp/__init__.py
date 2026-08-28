"""MCP plugin (RFC-0019, M3): client + server.

Speaks the Model Context Protocol (JSON-RPC 2.0) over **stdio** (local servers)
and **streamable HTTP** (remote servers) using only the standard library. The
**client** half (``McpClient`` / ``McpPlugin``) turns each configured server's
``tools/list`` into one typed :class:`~xyberos.contracts.Tool` per server tool.
The **server** half (``build_server`` / ``expose``) turns a Xyberos app's
registered tools into an MCP server for external clients (requires the
``[mcp]`` extra).
"""

from .client import McpClient
from .errors import McpError, McpSecurityError, McpTimeoutError
from .plugin import McpPlugin
from .registry import ServerConfig, load_servers
from .security import ServerAllowlist
from .server import build_server, expose

__all__ = [
    "McpClient",
    "McpError",
    "McpPlugin",
    "McpSecurityError",
    "McpTimeoutError",
    "ServerAllowlist",
    "ServerConfig",
    "build_server",
    "expose",
    "load_servers",
]

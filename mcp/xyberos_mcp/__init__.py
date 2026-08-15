"""MCP client plugin (RFC-0019, M3).

Speaks the Model Context Protocol (JSON-RPC 2.0) over **stdio** (local servers)
and **streamable HTTP** (remote servers) using only the standard library.
``tools/list`` on each configured server becomes one typed
:class:`~xyberos.contracts.Tool` per server tool, with arguments coerced
through :class:`~xyberos.tools.FunctionTool`.
"""

from .client import McpClient
from .errors import McpError, McpSecurityError, McpTimeoutError
from .plugin import McpPlugin
from .registry import ServerConfig, load_servers
from .security import ServerAllowlist

__all__ = [
    "McpClient",
    "McpError",
    "McpPlugin",
    "McpSecurityError",
    "McpTimeoutError",
    "ServerAllowlist",
    "ServerConfig",
    "load_servers",
]

# xyberos-mcp

**Model Context Protocol client plugin — RFC-0019, M3.** Xyberos → MCP →
an enormous ecosystem. Speaks the MCP protocol (JSON-RPC 2.0) over **stdio**
(local servers) and **streamable HTTP** (remote servers) using only the
standard library. Each configured server's `tools/list` becomes one typed
`Tool` (named `{server}_{tool}`), with arguments coerced through
`FunctionTool` / `coerce_arguments`.

## Install

```bash
pip install -e ./mcp
```

The client is stdlib-only; the `[mcp]` optional extra installs the official SDK
(not required). `xyberos[mcp]` is also declared in the core extras.

## Usage

```python
from xyberos import create_app
from xyberos_mcp import McpPlugin

servers = {
    "demo": {"command": ["python", "examples/demo_mcp_server.py"]},
    "remote": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ..."}},
}

app = create_app()
app.load_plugin(McpPlugin(servers))

app.tools.execute("demo_echo", None, text="hello", repeat=2)
```

Or configure entirely through the environment (`MCP_SERVERS` = JSON path or
inline JSON). An unconfigured instance registers nothing (logs a warning).

### Direct client use

```python
from xyberos_mcp import McpClient
from xyberos_mcp.registry import ServerConfig

with McpClient(ServerConfig(name="demo", command=["python", "demo_mcp_server.py"])) as client:
    client.list_tools()          # -> [{name, description, inputSchema}]
    client.call_tool("echo", {"text": "hi"})
```

## Design

- **Transports** — `StdioTransport` (newline-delimited JSON-RPC over a
  subprocess) and `HttpTransport` (streamable HTTP; handles `application/json`
  **and** `text/event-stream` responses).
- **Lifecycle** — `connect`/`disconnect`/`reconnect`, `initialize` handshake +
  `notifications/initialized`, per-request timeouts, and `utils.resilience.retry`
  on connect.
- **Security** — `shell=False` + literal argv (no shell interpolation), new
  session / hidden-window subprocess isolation, and a `ServerAllowlist` that
  refuses unlisted servers.
- **Typed tools** — MCP `inputSchema` → `FunctionTool` signature (same
  `__signature__` technique as the M2 HTTP connector).

## Examples

- `examples/demo_mcp_server.py` — a minimal local MCP server (`echo`, `add`).
- `examples/mcp_client.py` — connects to it, lists tools, calls one.
- `examples/servers.json` — stdio + remote HTTP config reference.

## Tests

```bash
pip install pytest
pytest tests/
```

The tests launch the bundled fake MCP server (stdio) and a local HTTP endpoint
(both `application/json` and SSE modes) — no external network, no SDK.

## Ship location

Plugin (`xyberos.plugins` entry point) + optional `[mcp]` extra. Depends on
M2's HTTP/typed-tool patterns.

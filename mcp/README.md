# xyberos-mcp

**The server direction of the MCP seam: an application's registered tools, offered to an MCP client.**

0.2.2's client, its stdio transport, and its `xyberos.plugins` entry point do not return. The client
lives in the core package as `xyberos.mcp`, because consuming another server's tools is a core
capability rather than a plugin's; the entry point is gone because this distribution is not a plugin
— it registers a route, and nothing else; and the stdio transport is **withheld** pending the
project owner's explicit approval, because spawning a process is a policy decision rather than a
transport detail.

What this version carries is the server direction and nothing else: `expose()`, over the core HTTP
adapter.

The point of the package is that an application's tool is exposed as itself. A
[`Tool`](https://github.com/xyberos/xyberos2.0/blob/master/docs/ai.md) the application already
registered reaches the client with its schema untouched, and a call runs through the same
validation and result handling a local tool call runs through — so there is no second code path, and
no schema that a caller can quietly widen.

## Install

```bash
pip install xyberos-mcp
```

## Expose an application's tools

```python
from xyberos import App
from xyberos.ai import Tool, ToolSpec
from xyberos.http import HttpAdapter
from xyberos_mcp import expose


async def search(arguments, context):
    return f"3 results for {arguments['query']}"


app = App()
expose(
    app,
    [
        Tool(
            spec=ToolSpec(
                name="search",
                description="Search the index.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            handler=search,
        )
    ],
    path="/mcp",           # where a client is pointed
    server_name="xyberos",  # what the handshake reports
)

asgi_app = HttpAdapter(app).asgi_app
```

`expose` registers `POST /mcp` on the application and returns the `McpServer` that answers on it.
The route is ordinary: it appears in `app.routes`, and the adapter serves it with the middleware,
error policy, and test client every other route gets, so serving an MCP client installs nothing new.
Point the client at `http://host:port/mcp`.

## What it answers

| Method | Answer |
| --- | --- |
| `initialize` | the revision in `SUPPORTED_PROTOCOL_VERSION`, `tools.listChanged: false`, and this server's name and version |
| `notifications/initialized` | nothing — a notification is owed no reply |
| `tools/list` | every tool of the set, with the `inputSchema` and description the application declared |
| `tools/call` | one text content block: the handler's own text, or its value JSON-encoded |

Prompts, resources, sampling, and server-initiated notifications are not implemented, exactly as the
client half does not implement them: the two halves cover the same subset of the protocol, so a
client that works against one works against the other. An unknown method is answered with `-32601`,
naming what this server does implement; an unknown notification is ignored, because a notification
has no reply to carry an error.

The server is stateless. It issues no session, it does not require `initialize` before `tools/list`,
and the tool set is read once when the server is built — which is why a client's cached tool list
stays correct for as long as the route answers, and why `listChanged` is `false`.

The transport is the streamable HTTP channel's `POST` and nothing else. The `GET`/event-stream
channel is absent because the client half never sends anything over it.

## Failures

A tool that fails is a **JSON-RPC error**, not an HTTP status. That is the whole design of this
table:

| What happened | Reply |
| --- | --- |
| the body is not JSON | HTTP `400`, `-32700`, `id: null` |
| the message is not a JSON-RPC request: not an object, a batch, another `jsonrpc` revision, no `method` | HTTP `400`, `-32600` |
| the method is not one of the four above | `200`, `-32601` |
| the tool name is unknown, or the arguments are not an object | `200`, `-32602`, naming the tools that are offered |
| the arguments fail the tool's own schema | `200`, `-32602`, with the schema error verbatim |
| the handler raised | `200`, `-32603`, with the tool, the error type, and the message in the fault's `data` |

A handler that raised and escaped the route would reach the client as an HTTP `500` whose body is
not a JSON-RPC reply — the client would report a protocol error and the cause would be gone with it.
So the cause travels: `{"code": -32603, "message": "tool 'search' failed: RuntimeError: the index is
down", "data": {"tool": "search", "errorType": "RuntimeError"}}`. A `400` is reserved for a message
the server could not read as a request at all; everything a request earned is a `200` carrying the
code and the message that were meant for it, and a notification is `202` with no body.

Settings are refused where they are declared, with the framework's own errors: `McpConfigurationError`
for an empty tool set, a name that repeats, something that is not a `Tool`, or a blank server name;
`RouteRegistrationError` for a path that is not a route template; and `LifecycleStateError` for an
`expose` after the application started.

## Authorization

This route enforces no identity and no authorization, and it does not pretend to. The framework has
no identity, tenancy, or authorization model to put in front of an RPC surface and will not grow one
([ADR 0014](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md)),
so the caller brings one: a verifier as adapter middleware (`HttpAdapter(app, middleware=(...))`), or
an edge that strips client-supplied assertion headers before they arrive. What this package owes is
the warning, and it is this paragraph.

## Tests

```bash
python -m pytest tests -q
```

The core repository ships no conformance suite for this seam, so `packages.toml` keeps this name
`planned` and the package's own tests are the gate. They drive the exposed server with a stub
JSON-RPC client over the adapter's in-process test client: no subprocesses, no sockets beyond it, and
no network.

## What it does not do

- **No client.** Consuming a server's tools is `xyberos.mcp` in the core package. Two distributions
  answering for one protocol is two answers to one question.
- **No stdio transport.** Withheld pending the project owner's explicit approval; not implemented,
  not exported, and not promised here.
- **No identity or authorization model.** See above: the caller brings one.
- **No sessions, prompts, resources, or sampling.** The first because the server holds nothing
  between requests, the rest because the client half does not speak them either.

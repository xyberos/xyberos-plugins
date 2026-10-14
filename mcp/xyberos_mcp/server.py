"""Serve an application's registered tools to an MCP client.

An MCP client speaks JSON-RPC 2.0 to a URL. This module is the other end of that conversation for a
Xyberos application: :func:`expose` registers a ``POST`` route that answers ``initialize``,
``tools/list``, and ``tools/call`` for the tools the application names, and the application serves
it the way it serves every other route — through the core HTTP adapter:

    from xyberos import App
    from xyberos.ai import Tool, ToolSpec
    from xyberos.http import HttpAdapter
    from xyberos_mcp import expose

    tool = Tool(spec=ToolSpec(name="search", description="...", parameters={...}), handler=search)

    app = App()
    expose(app, [tool])
    asgi_app = HttpAdapter(app).asgi_app

Three things about this surface are decisions rather than omissions, and a reader should meet them
here rather than discover them:

* **The client is not in this distribution.** Consuming another server's tools ships with the core
  package as ``xyberos.mcp``; this package is the server direction only, so one name answers one
  question instead of two.
* **There is no stdio transport.** Spawning a process is a policy decision rather than a transport
  detail, so it is withheld until the project owner approves it; nothing here implements or exports
  one.
* **The caller brings authorization.** The framework has no identity, tenancy, or authorization
  model to put in front of an RPC surface ([ADR 0014]), so this package states that rather than
  growing a half-built one.

[ADR 0014]: https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

try:
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
except ModuleNotFoundError as error:  # pragma: no cover - a broken install, not a code path
    raise ModuleNotFoundError(
        "xyberos-mcp needs Starlette, which arrives with the core package's http extra that this "
        "distribution declares as a dependency: reinstall it with 'pip install \"xyberos-mcp\"' "
        f"({error})"
    ) from error

from xyberos.ai.contracts import ToolCall
from xyberos.ai.tools import Tool, ToolSet
from xyberos.app import App
from xyberos.errors import AIToolError, McpConfigurationError, McpError, McpProtocolError
from xyberos_mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSONRPC_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSION,
    JsonRpcFault,
    as_mapping,
    as_text,
    error_reply,
    result_reply,
)
from xyberos_mcp.tools import call_result, failed_call, tool_entry

__all__ = ["SERVER_NAME", "McpServer", "expose"]

SERVER_NAME = "xyberos"
"""The name this server reports during initialization, mirroring the client's ``CLIENT_NAME``.

The handshake is where the two sides introduce themselves, and both halves of this seam belong to
Xyberos; the *distribution* is named in the handshake's version instead.
"""

_NOTIFICATION_PREFIX = "notifications/"
_IMPLEMENTED_METHODS = "initialize, notifications/initialized, tools/list, and tools/call"


def _distribution_version() -> str:
    """Return the version of this distribution, or a marker when it is not installed.

    A source checkout has no distribution metadata, and a version invented for one would be a lie a
    client reports: ``0+unknown`` says what it is, and a wheel that was installed says ``0.3.0``.
    """
    try:
        return distribution_version("xyberos-mcp")
    except PackageNotFoundError:
        return "0+unknown"


_SERVER_VERSION = _distribution_version()


def _ordered(tools: ToolSet) -> tuple[Tool, ...]:
    """Return the tools of a set, in registration order."""
    return tuple(tool for tool in (tools.get(name) for name in tools.names) if tool is not None)


def _snapshot(tools: ToolSet | Iterable[Tool]) -> tuple[Tool, ...]:
    """Return ``tools`` as a tuple, without walking a set twice."""
    if isinstance(tools, ToolSet):
        return _ordered(tools)
    return tuple(tools)


def _tool_set(tools: ToolSet | Iterable[Tool]) -> ToolSet:
    """Return the tools a server offers as one core tool set, refusing a set it cannot serve.

    The validation is the core model's — :class:`~xyberos.ai.tools.ToolSet` already refuses a name
    that repeats and something that is not a :class:`~xyberos.ai.tools.Tool` — and the refusal is
    restated as a configuration error because a tool set is this server's configuration. An empty
    set is refused here for the reason the client refuses an empty opt-in: a server with nothing to
    offer is a mistake or a server nobody needs, and both are cheaper to catch now than on the wire.
    """
    try:
        tool_set = ToolSet(_snapshot(tools))
    except AIToolError as error:
        raise McpConfigurationError(
            f"the tools a server exposes must be Tools with distinct names: {error}"
        ) from error
    if not tool_set.names:
        raise McpConfigurationError(
            "a server needs at least one tool to expose; a server with nothing to offer answers "
            "tools/list with nothing, which is a mistake or a server nobody needs"
        )
    return tool_set


class McpServer:
    """One MCP server: the tools it offers, and the JSON-RPC methods that answer for them.

    The type is transport-free on purpose. :meth:`handle` answers one JSON-RPC message, and
    :func:`expose` is what binds it to a route, so the protocol can be driven directly — in a test,
    or from code that already has a transport — and nothing here has an opinion about HTTP.
    """

    def __init__(self, tools: ToolSet | Iterable[Tool], *, server_name: str = SERVER_NAME) -> None:
        """Build a server that offers ``tools``.

        The tools are read once, here: a caller that mutates the collection it passed afterwards
        does not change what this server offers, which is what makes the tool list a client caches
        correct for as long as the server answers.
        """
        name = server_name.strip()
        if not name:
            raise McpConfigurationError(
                "the server name must be a non-empty string, because it is what a client reports "
                "it is talking to"
            )
        self._server_name = name
        self._tools = _tool_set(tools)

    @property
    def name(self) -> str:
        """The name this server reports during initialization."""
        return self._server_name

    @property
    def tools(self) -> tuple[Tool, ...]:
        """The tools this server offers, in registration order."""
        return _ordered(self._tools)

    def list_tools(self) -> tuple[dict[str, object], ...]:
        """Return the tools as the entries ``tools/list`` answers with."""
        return tuple(tool_entry(tool) for tool in self.tools)

    async def handle(self, message: object) -> dict[str, object] | None:
        """Answer one JSON-RPC message, and return ``None`` when nothing is owed.

        A message that is not a JSON-RPC request this server can answer raises
        :class:`~xyberos.errors.McpProtocolError`, because there is no request to reply *to*. A
        message it did read is always answered — with a result, or with an error naming what went
        wrong — and a notification is answered with nothing at all, which is what makes a client's
        ``notifications/initialized`` a no-op rather than a reply it never asked for.
        """
        request = as_mapping(message)
        if request is None:
            raise McpProtocolError(
                f"an MCP message must be a JSON-RPC object, not {type(message).__name__}"
            )
        version = request.get("jsonrpc")
        if version != JSONRPC_VERSION:
            raise McpProtocolError(
                f'an MCP request must carry "jsonrpc": "2.0", not {version!r}'
            )
        method = as_text(request.get("method"))
        if method is None:
            raise McpProtocolError("an MCP request must carry a non-empty 'method' string")
        outcome = await self._dispatch(method, request.get("params"))
        if "id" not in request:
            # A notification is owed nothing, whatever it earned, so the fault is dropped here
            # rather than answered: a reply to a notification is a protocol violation in itself.
            return None
        if isinstance(outcome, JsonRpcFault):
            return outcome.reply(request.get("id"))
        return result_reply(request.get("id"), outcome)

    async def _dispatch(
        self, method: str, params: object
    ) -> Mapping[str, object] | JsonRpcFault:
        """Answer one method, or return the fault that method's request earned."""
        if method == "initialize":
            return self._initialize(params)
        if method.startswith(_NOTIFICATION_PREFIX):
            # A notification is owed no reply at all, so accepting one this server does not know is
            # the same answer as accepting one it does: nothing.
            return {}
        if method == "tools/list":
            return {"tools": list(self.list_tools())}
        if method == "tools/call":
            return await self._call(params)
        return JsonRpcFault(
            METHOD_NOT_FOUND, f"this server implements {_IMPLEMENTED_METHODS}, not {method!r}"
        )

    def _initialize(self, params: object) -> Mapping[str, object] | JsonRpcFault:
        """Answer ``initialize``, which is where the two sides agree on a revision.

        This server answers with the revision it speaks and leaves the judgment to the client,
        which is the only side that knows what it needs: the client half refuses a server that
        negotiated a different revision, naming both, rather than guessing which side is wrong.
        """
        declared = as_mapping({} if params is None else params)
        if declared is None:
            return JsonRpcFault(INVALID_PARAMS, "the params of initialize must be an object")
        if as_text(declared.get("protocolVersion")) is None:
            return JsonRpcFault(
                INVALID_PARAMS, "the params of initialize must name a protocolVersion"
            )
        return {
            "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self._server_name, "version": _SERVER_VERSION},
        }

    async def _call(self, params: object) -> Mapping[str, object] | JsonRpcFault:
        """Answer ``tools/call`` by running one tool of this server's set.

        The call runs through the core tool model, so the arguments are validated against the tool's
        own schema before the handler sees them, and a handler that raises is a result rather than
        an exception escaping through the transport. Both then leave here as a JSON-RPC error whose
        message names the tool and the cause, which is what a client can report.
        """
        declared = as_mapping({} if params is None else params)
        if declared is None:
            return JsonRpcFault(INVALID_PARAMS, "the params of tools/call must be an object")
        name = as_text(declared.get("name"))
        if name is None:
            return JsonRpcFault(INVALID_PARAMS, "the params of tools/call must name a tool")
        arguments = as_mapping(declared.get("arguments", {}))
        if arguments is None:
            return JsonRpcFault(
                INVALID_PARAMS, f"the arguments of tool {name!r} must be an object"
            )
        if name not in self._tools:
            offered = ", ".join(self._tools.names) or "none"
            return JsonRpcFault(
                INVALID_PARAMS, f"this server offers no tool named {name!r}; it offers: {offered}"
            )
        result = await self._tools.invoke(ToolCall(name=name, arguments=dict(arguments)))
        if not result.ok:
            return failed_call(name, result)
        return call_result(result.value)


def expose(
    app: App,
    tools: ToolSet | Iterable[Tool],
    *,
    path: str = "/mcp",
    server_name: str = SERVER_NAME,
) -> McpServer:
    """Register ``POST path`` on ``app`` and return the server that answers on it.

    The route is ordinary: it is registered before the application starts, it appears in
    ``app.routes``, and the core HTTP adapter serves it with the same middleware, error policy, and
    test client as every other route. What the endpoint adds is the one thing an RPC surface needs —
    a JSON-RPC error is a *reply*, so a tool that fails reaches the client with its cause instead of
    becoming an HTTP 500 that hides it.

    Nothing here authenticates the caller. The framework ships no identity or authorization model to
    put in front of an RPC surface ([ADR 0014]), so verification stays the deployment's, and the
    middleware ``HttpAdapter`` already takes is where the sanctioned verifier goes.

    [ADR 0014]: https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md
    """
    server = McpServer(tools, server_name=server_name)
    app.route("POST", path, _endpoint(server), name=f"MCP {path}")
    return server


def _endpoint(server: McpServer) -> Callable[[Request], Awaitable[Response]]:
    """Return the route handler that answers JSON-RPC for ``server``.

    Two statuses separate two kinds of failure. A body this server could not read as a JSON-RPC
    request is refused with ``400`` and an error body that still names the code, because there is no
    request to answer. Everything a request earned — a result, or an error about the tool it named —
    is ``200``, so the client reads the code and the message that were meant for it. A notification
    is ``202`` with no body, which is what "owes no reply" looks like over HTTP.
    """

    async def endpoint(request: Request) -> Response:
        raw = await request.body()
        try:
            message: object = json.loads(raw)
        except ValueError:
            return JSONResponse(
                error_reply(None, PARSE_ERROR, "the request body is not valid JSON"),
                status_code=400,
            )
        try:
            reply = await server.handle(message)
        except McpProtocolError as fault:
            return JSONResponse(
                error_reply(_request_id(message), INVALID_REQUEST, str(fault)), status_code=400
            )
        except McpError as fault:
            return JSONResponse(
                error_reply(_request_id(message), INTERNAL_ERROR, str(fault)), status_code=400
            )
        if reply is None:
            return Response(status_code=202)
        return JSONResponse(reply)

    return endpoint


def _request_id(message: object) -> object:
    """Return the id to answer with, or ``None`` when the message could not supply one.

    An error for a request that could not be read carries a null id, which is the signal a client
    needs: the reply it is about to receive is not about anything it can match up.
    """
    envelope = as_mapping(message)
    if envelope is None:
        return None
    identifier = envelope.get("id")
    if isinstance(identifier, (str, int, float)):
        return identifier
    return None

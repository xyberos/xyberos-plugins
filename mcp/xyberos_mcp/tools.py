"""Project the core tool model onto the MCP surface, and a call's outcome back.

An MCP client asks which tools a server offers and then calls one by name. Both directions are the
core model's: the :class:`~xyberos.ai.tools.Tool` an application registered is what travels, so its
schema reaches the client untouched, and a call runs through the validation and result handling a
local call runs through. Only the framing is MCP's — a tool is a ``name``/``description``/
``inputSchema`` object, and an answer is a content block carrying text.
"""

from __future__ import annotations

import json

from xyberos.ai.tools import Tool, ToolResult
from xyberos.errors import AISchemaError
from xyberos_mcp.protocol import INTERNAL_ERROR, INVALID_PARAMS, JsonRpcFault

__all__ = ["call_result", "failed_call", "tool_entry"]


def tool_entry(tool: Tool) -> dict[str, object]:
    """Return one registered tool as the ``tools/list`` entry a client reads.

    The description travels verbatim and the schema travels unchanged, because both are what the
    application declared: a server that shortened or rewrote either would be answering for the
    application rather than reporting it. The schema is the more important half — it is what the
    client shows a model and what the arguments are checked against here.
    """
    return {
        "name": tool.spec.name,
        "description": tool.spec.description,
        "inputSchema": dict(tool.spec.parameters),
    }


def call_result(value: object) -> dict[str, object]:
    """Return a successful call as the ``tools/call`` result a client reads.

    ``isError`` is written out rather than omitted even though it is always false here, because it
    is what a client branches on: a tool that fails is a JSON-RPC error instead (see
    :func:`failed_call`), so a result that arrived is a result that ran.
    """
    return {"content": [{"type": "text", "text": text_of(value)}], "isError": False}


def failed_call(name: str, result: ToolResult) -> JsonRpcFault:
    """Return the JSON-RPC error a failed call earned.

    The cause is the point of the reply. Arguments the tool's own schema rejects are
    ``INVALID_PARAMS``, because the caller can fix those; a handler that raised is ``INTERNAL_ERROR``
    with the error type and the message in the fault, so a client reports what actually went wrong
    instead of a generic failure that names nothing.
    """
    data: dict[str, object] = {"tool": name, "errorType": result.error_type}
    if result.error_type == AISchemaError.__name__:
        return JsonRpcFault(
            INVALID_PARAMS,
            f"the arguments of tool {name!r} do not satisfy its schema: {result.error}",
            data=data,
        )
    return JsonRpcFault(INTERNAL_ERROR, f"tool {name!r} failed: {_cause(result)}", data=data)


def text_of(value: object) -> str:
    """Return a handler's value as the text of one content block.

    Text is sent verbatim, because a tool that answers with text has already said what it meant.
    Anything else is JSON-encoded rather than stringified, because the client asked for the tool's
    answer and a Python repr is not it. A value JSON cannot carry at all falls back to its repr,
    because a silently empty result is worse than an ugly one.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return repr(value)


def _cause(result: ToolResult) -> str:
    """Return the error type and message of a failed call, as one phrase."""
    kind = result.error_type or "an error"
    detail = result.error or "the handler gave no message"
    return f"{kind}: {detail}"

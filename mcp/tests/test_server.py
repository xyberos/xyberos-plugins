"""What the exposed server promises a client, driven over the core HTTP adapter.

The tests are ordinary pytest tests: an async scenario is a synchronous test calling
``asyncio.run(...)``. Every message goes through ``create_test_client(HttpAdapter(app))``, so the
route, the adapter's middleware, and the JSON-RPC surface are exercised together — with no
subprocess, no socket beyond that in-process client, and no network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager

import httpx
import pytest
from starlette.testclient import TestClient

from xyberos import App
from xyberos.ai import Tool, ToolContext, ToolSpec
from xyberos.errors import McpProtocolError
from xyberos.http import HttpAdapter
from xyberos.http.testing import create_test_client
from xyberos_mcp import SERVER_NAME, SUPPORTED_PROTOCOL_VERSION, McpServer, expose
from xyberos_mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)

PATH = "/mcp"

ECHO_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"text": {"type": "string", "minLength": 1}},
    "required": ["text"],
    "additionalProperties": False,
}
"""A schema inside the closed subset the core validates, so a call can be refused for its arguments."""


class StubClient:
    """A raw JSON-RPC client for the exposed server, over the adapter's test client.

    It is deliberately not the core client. This suite is about the server's side of the wire, so
    the stub writes messages by hand and reads replies by hand, and nothing under test is reused to
    check the thing under test.
    """

    def __init__(self, client: TestClient, path: str = PATH) -> None:
        self._client = client
        self._path = path
        self._next_id = 0

    def post(self, message: object) -> httpx.Response:
        """POST one already-built message and return the raw HTTP response."""
        return self._client.post(self._path, json=message)

    def raw(self, body: bytes) -> httpx.Response:
        """POST a body that is not JSON at all."""
        return self._client.post(self._path, content=body)

    def send(
        self, method: str, params: object = None, *, notification: bool = False
    ) -> httpx.Response:
        """POST one JSON-RPC message, numbered unless it is a notification."""
        payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self._next_id += 1
            payload["id"] = self._next_id
        return self.post(payload)

    def reply(self, method: str, params: object = None) -> Mapping[str, object]:
        """POST one request and return the whole reply, which must have been answered with a 200."""
        response = self.send(method, params)
        assert response.status_code == 200, response.text
        payload: object = response.json()
        assert isinstance(payload, dict)
        return payload

    def result(self, method: str, params: object = None) -> Mapping[str, object]:
        """POST one request and return its result, insisting there was no error."""
        reply = self.reply(method, params)
        assert "error" not in reply, reply
        result = reply.get("result")
        assert isinstance(result, dict)
        return result

    def fault(self, method: str, params: object = None) -> Mapping[str, object]:
        """POST one request and return its JSON-RPC error, insisting there was no result."""
        reply = self.reply(method, params)
        assert "result" not in reply, reply
        error = reply.get("error")
        assert isinstance(error, dict)
        return error

    def initialize(
        self, protocol_version: str = SUPPORTED_PROTOCOL_VERSION
    ) -> Mapping[str, object]:
        """Perform the handshake the shipped client performs."""
        return self.result(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "stub", "version": "1"},
            },
        )

    def tool_entries(self) -> list[dict[str, object]]:
        """Return the ``tools/list`` entries."""
        tools = self.result("tools/list").get("tools")
        assert isinstance(tools, list)
        return tools

    def call(self, name: str, arguments: Mapping[str, object]) -> Mapping[str, object]:
        """Call one tool and return the ``tools/call`` result."""
        return self.result("tools/call", {"name": name, "arguments": arguments})

    def text(self, name: str, arguments: Mapping[str, object]) -> str:
        """Call one tool and return the text of its first content block."""
        content = self.call(name, arguments).get("content")
        assert isinstance(content, list) and content
        block = content[0]
        assert isinstance(block, dict)
        return str(block["text"])


@contextmanager
def serving(
    tools: Iterable[Tool],
    *,
    path: str = PATH,
    server_name: str = SERVER_NAME,
) -> Iterator[StubClient]:
    """Yield a stub client for an application that exposes ``tools`` on ``path``."""
    app = App()
    expose(app, tools, path=path, server_name=server_name)
    with create_test_client(HttpAdapter(app)) as client:
        yield StubClient(client, path)


def echo_tool(
    *,
    description: str = "Return what it was given.",
    seen: list[Mapping[str, object]] | None = None,
) -> Tool:
    """A tool that returns its argument as text, and records the arguments it was handed."""

    async def handler(arguments: Mapping[str, object], context: ToolContext) -> str:
        if seen is not None:
            seen.append(dict(arguments))
        return f"echo: {arguments['text']}"

    return Tool(
        spec=ToolSpec(name="echo", description=description, parameters=ECHO_SCHEMA),
        handler=handler,
    )


def counting_tool() -> Tool:
    """A tool that answers with a value rather than with text."""

    async def handler(arguments: Mapping[str, object], context: ToolContext) -> object:
        up_to = arguments["up_to"]
        assert isinstance(up_to, int)
        return {"total": sum(range(1, up_to + 1))}

    return Tool(
        spec=ToolSpec(
            name="count",
            description="Add up to a number.",
            parameters={
                "type": "object",
                "properties": {"up_to": {"type": "integer", "minimum": 1}},
                "required": ["up_to"],
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )


def failing_tool() -> Tool:
    """A tool whose handler raises, which is the failure mode under test."""

    async def handler(arguments: Mapping[str, object], context: ToolContext) -> str:
        raise RuntimeError("the upstream service is down")

    return Tool(
        spec=ToolSpec(name="boom", description="Always fails.", parameters={"type": "object"}),
        handler=handler,
    )


def test_initialize_names_the_server_and_the_revision_it_speaks() -> None:
    with serving([echo_tool()], server_name="checkout") as rpc:
        result = rpc.initialize()

    assert result["protocolVersion"] == SUPPORTED_PROTOCOL_VERSION
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    server_info = result["serverInfo"]
    assert isinstance(server_info, dict)
    assert server_info["name"] == "checkout"
    assert isinstance(server_info["version"], str)
    assert server_info["version"], "a client reports the version it was told"


def test_initialize_answers_with_this_revision_rather_than_the_one_requested() -> None:
    """The client half refuses a server that negotiated another revision, naming both, so the
    server reports what it speaks instead of agreeing to something it cannot do."""
    with serving([echo_tool()]) as rpc:
        result = rpc.initialize(protocol_version="2024-11-05")

    assert result["protocolVersion"] == SUPPORTED_PROTOCOL_VERSION


def test_initialize_needs_to_be_told_which_revision_the_client_speaks() -> None:
    with serving([echo_tool()]) as rpc:
        error = rpc.fault("initialize", {"capabilities": {}, "clientInfo": {"name": "stub"}})

    assert error["code"] == INVALID_PARAMS
    assert "protocolVersion" in str(error["message"])


def test_the_initialized_notification_is_answered_with_an_accepted_response_and_no_body() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.send("notifications/initialized", notification=True)

    assert response.status_code == 202
    assert response.content == b"", "a notification is owed no body, and none is sent"


def test_an_unknown_notification_is_ignored_because_it_has_no_reply_to_carry() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.send("notifications/something-new", notification=True)

    assert response.status_code == 202


def test_a_registered_tool_is_offered_with_its_schema_and_description_intact() -> None:
    description = "Return what it was given. " * 100

    with serving([echo_tool(description=description)]) as rpc:
        entries = rpc.tool_entries()

    assert [entry["name"] for entry in entries] == ["echo"]
    assert entries[0]["inputSchema"] == ECHO_SCHEMA, "the schema is what validates the arguments"
    assert entries[0]["description"] == description, (
        "the description is the application's, so the server never shortens it"
    )


def test_tools_call_returns_the_handler_s_text_and_hands_it_validated_arguments() -> None:
    seen: list[Mapping[str, object]] = []

    with serving([echo_tool(seen=seen)]) as rpc:
        result = rpc.call("echo", {"text": "hello"})

    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": "echo: hello"}]
    assert seen == [{"text": "hello"}]


def test_a_tool_that_answers_with_something_other_than_text_is_json_encoded() -> None:
    with serving([counting_tool()]) as rpc:
        assert rpc.text("count", {"up_to": 3}) == '{"total": 6}'


def test_a_tool_that_raises_is_a_json_rpc_error_that_carries_the_cause() -> None:
    """The failure is the *reply*, not a status: a 500 would reach the client as a body it cannot
    read as JSON-RPC, and the tool's own error would be gone with it."""
    with serving([failing_tool(), echo_tool()]) as rpc:
        response = rpc.send("tools/call", {"name": "boom", "arguments": {}})

        assert response.status_code == 200, "a failing tool is an answer, not a transport failure"
        payload = response.json()
        assert "result" not in payload
        error = payload["error"]
        assert error["code"] == INTERNAL_ERROR
        assert "boom" in error["message"]
        assert "RuntimeError: the upstream service is down" in error["message"]
        assert error["data"] == {"tool": "boom", "errorType": "RuntimeError"}

        assert rpc.text("echo", {"text": "still here"}) == "echo: still here", (
            "one tool failing says nothing about the others"
        )


def test_arguments_the_schema_rejects_are_refused_before_the_handler_sees_them() -> None:
    seen: list[Mapping[str, object]] = []

    with serving([echo_tool(seen=seen)]) as rpc:
        missing = rpc.fault("tools/call", {"name": "echo", "arguments": {}})
        too_short = rpc.fault("tools/call", {"name": "echo", "arguments": {"text": ""}})

    assert missing["code"] == INVALID_PARAMS
    assert "missing the required property 'text'" in str(missing["message"])
    assert too_short["code"] == INVALID_PARAMS
    assert seen == [], "a call the schema refuses must never reach the handler"


def test_an_unknown_tool_is_refused_with_the_names_that_are_offered() -> None:
    with serving([echo_tool(), counting_tool()]) as rpc:
        error = rpc.fault("tools/call", {"name": "search", "arguments": {}})

    assert error["code"] == INVALID_PARAMS
    assert "'search'" in str(error["message"])
    assert "echo, count" in str(error["message"])


def test_arguments_that_are_not_an_object_are_refused() -> None:
    with serving([echo_tool()]) as rpc:
        error = rpc.fault("tools/call", {"name": "echo", "arguments": "hello"})

    assert error["code"] == INVALID_PARAMS
    assert "must be an object" in str(error["message"])


def test_a_method_this_server_does_not_implement_is_refused_by_name() -> None:
    with serving([echo_tool()]) as rpc:
        error = rpc.fault("resources/list", {})

    assert error["code"] == METHOD_NOT_FOUND
    assert "tools/list" in str(error["message"]), "the refusal says what is implemented"


def test_a_body_that_is_not_json_is_a_parse_error_and_an_http_refusal() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.raw(b"{not json")

    assert response.status_code == 400, "no request was read, so there is no request to answer"
    payload = response.json()
    assert payload["id"] is None
    assert payload["error"]["code"] == PARSE_ERROR


def test_a_batch_is_refused_because_no_party_to_this_seam_sends_one() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.post([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])

    assert response.status_code == 400
    payload = response.json()
    assert payload["id"] is None
    assert payload["error"]["code"] == INVALID_REQUEST


def test_a_message_that_is_not_a_json_rpc_object_is_refused() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.post("hello")

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == INVALID_REQUEST
    assert "str" in payload["error"]["message"]


def test_a_request_declaring_another_json_rpc_revision_is_refused_with_its_own_id() -> None:
    with serving([echo_tool()]) as rpc:
        response = rpc.post({"jsonrpc": "1.0", "id": 7, "method": "tools/list"})

    payload = response.json()
    assert payload["error"]["code"] == INVALID_REQUEST
    assert payload["id"] == 7, "a message that could be read keeps the id it was sent with"


@pytest.mark.parametrize("identifier", [1, "abc", 2.5])
def test_the_reply_carries_the_id_it_was_given_whatever_its_type(identifier: object) -> None:
    with serving([echo_tool()]) as rpc:
        payload = rpc.post(
            {"jsonrpc": "2.0", "id": identifier, "method": "tools/list"}
        ).json()

    assert payload["id"] == identifier


def test_the_python_facing_handler_raises_for_a_message_it_cannot_answer() -> None:
    """A reply is owed to a *request*. A message that is not one has nothing to reply to, so the
    Python caller gets the error the wire turns into a refusal."""
    server = McpServer([echo_tool()])

    async def scenario() -> None:
        with pytest.raises(McpProtocolError, match="must be a JSON-RPC object"):
            await server.handle([])
        with pytest.raises(McpProtocolError, match="non-empty 'method'"):
            await server.handle({"jsonrpc": "2.0", "id": 1})

        assert (
            await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        )

        listed = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert listed is not None
        result = listed["result"]
        assert isinstance(result, dict)
        assert [entry["name"] for entry in result["tools"]] == ["echo"]

    asyncio.run(scenario())

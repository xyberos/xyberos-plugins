"""What ``expose`` and ``McpServer`` refuse before a client ever connects.

A server's tool set is its configuration, so an unusable one is refused where it was declared — with
the framework's own error types, and with the message that says which input was the problem — rather
than on the first call a client makes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import cast

import pytest

from xyberos import App, LifecycleStateError
from xyberos.ai import Tool, ToolContext, ToolSet, ToolSpec
from xyberos.errors import McpConfigurationError, RouteRegistrationError
from xyberos_mcp import McpServer, expose


def a_tool(name: str = "echo") -> Tool:
    """A tool with nothing to validate, which is all a configuration test needs."""

    async def handler(arguments: Mapping[str, object], context: ToolContext) -> str:
        return "ok"

    return Tool(spec=ToolSpec(name=name), handler=handler)


def test_a_server_with_nothing_to_expose_is_refused() -> None:
    with pytest.raises(McpConfigurationError, match="at least one tool"):
        McpServer([])


def test_a_tool_set_with_a_name_that_repeats_is_refused() -> None:
    with pytest.raises(McpConfigurationError, match="distinct names"):
        McpServer([a_tool(), a_tool()])


def test_something_that_is_not_a_tool_is_refused() -> None:
    declared = cast("Iterable[Tool]", [a_tool(), "echo"])

    with pytest.raises(McpConfigurationError, match="distinct names"):
        McpServer(declared)


def test_a_server_name_that_is_blank_is_refused() -> None:
    with pytest.raises(McpConfigurationError, match="non-empty string"):
        McpServer([a_tool()], server_name="   ")


def test_a_tool_set_the_application_already_has_is_accepted() -> None:
    server = McpServer(ToolSet.of(a_tool()))

    assert [tool.spec.name for tool in server.tools] == ["echo"]
    assert [entry["name"] for entry in server.list_tools()] == ["echo"]


def test_expose_binds_the_server_to_a_route_the_adapter_serves() -> None:
    app = App()
    server = expose(app, [a_tool()], path="/tools")

    assert [(route.method, route.path, route.name) for route in app.routes] == [
        ("POST", "/tools", "MCP /tools")
    ]
    assert server.name == "xyberos"
    assert [tool.spec.name for tool in server.tools] == ["echo"]


def test_expose_defaults_to_the_path_a_client_is_pointed_at_first() -> None:
    app = App()
    expose(app, [a_tool()])

    assert [route.path for route in app.routes] == ["/mcp"]


def test_a_path_that_is_not_a_route_template_is_refused_by_the_route_registry() -> None:
    with pytest.raises(RouteRegistrationError, match="must start with '/'"):
        expose(App(), [a_tool()], path="mcp")


def test_expose_after_the_application_started_is_refused_like_any_other_registration() -> None:
    app = App()

    async def scenario() -> None:
        await app.start()
        try:
            with pytest.raises(LifecycleStateError, match="cannot register"):
                expose(app, [a_tool()])
        finally:
            await app.stop()

    asyncio.run(scenario())

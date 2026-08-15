"""Tests for typed tool generation from declared operations."""

from __future__ import annotations

import json

import pytest

from xyberos_http_api import HttpClient, HttpApiSpec, Operation, Param, build_operation_tool


def _spec(base_url: str, operation: Operation, **kwargs) -> HttpApiSpec:
    return HttpApiSpec(name="t", base_url=base_url, operations=[operation], **kwargs)


def test_tool_schema_is_typed(server):
    base_url, _ = server
    op = Operation(
        name="get_forecast",
        method="GET",
        path="/forecast",
        params=(
            Param("latitude", type="number", required=True),
            Param("longitude", type="number", required=True),
            Param("units", type="string", default="metric"),
            Param("active", type="boolean", required=False, default=True),
        ),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    schema = tool.schema
    assert schema["name"] == "get_forecast"
    props = schema["parameters"]["properties"]
    assert props["latitude"] == {"type": "number"}
    assert props["longitude"] == {"type": "number"}
    assert props["units"] == {"type": "string"}
    assert props["active"] == {"type": "boolean"}
    assert schema["parameters"]["required"] == ["latitude", "longitude"]


def test_tool_executes_and_coerces(server):
    base_url, _ = server
    op = Operation(
        name="get_forecast",
        path="/forecast",
        params=(
            Param("latitude", type="number", required=True),
            Param("longitude", type="number", required=True),
            Param("units", type="string", default="metric"),
        ),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    result = tool.execute(None, latitude="10.5", longitude="-66")
    assert result["latitude"] == 10.5  # coerced from string
    assert result["units"] == "metric"


def test_tool_missing_required_raises(server):
    base_url, _ = server
    op = Operation(
        name="get_forecast",
        path="/forecast",
        params=(Param("latitude", type="number", required=True),),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    with pytest.raises(Exception, match="latitude"):
        tool.execute(None)


def test_path_param_substitution(server):
    base_url, _ = server
    op = Operation(
        name="get_user",
        path="/users/{name}",
        params=(Param("name", in_="path", required=True),),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    result = tool.execute(None, name="baltz")
    assert result["login"] == "baltz"
    assert result["public_repos"] == 42


def test_header_param_sent(server):
    base_url, requests = server
    op = Operation(
        name="with_header",
        path="/users/baltz",
        params=(Param("X-Trace", in_="header", default="abc"),),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    # Non-identifier names are exposed under a sanitized signature name.
    assert "X_Trace" in tool.schema["parameters"]["properties"]
    tool.execute(None, X_Trace="abc")
    assert requests[0]["headers"].get("x-trace") == "abc"


def test_body_param(server):
    base_url, _ = server
    op = Operation(
        name="send",
        method="POST",
        path="/body",
        params=(Param("payload", in_="body", type="object", required=True),),
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    result = tool.execute(None, payload={"hello": "world"})
    assert result == {"received": {"hello": "world"}}


def test_response_path_extraction(server):
    base_url, _ = server
    op = Operation(
        name="temp",
        path="/forecast",
        params=(Param("latitude", type="number", required=True),),
        response_path="current_weather.temperature",
    )
    tool = build_operation_tool(_spec(base_url, op), op, HttpClient(base_url))
    assert tool.execute(None, latitude=1) == 21.5


def test_extract_path_with_indices():
    from xyberos_http_api.builder import extract_path

    data = {"a": [{"b": 7}, {"b": 8}]}
    assert extract_path(data, "a[1].b") == 8
    assert extract_path(data, "missing") is None
    assert extract_path(data, None) == data

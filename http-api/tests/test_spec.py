"""Tests for declarative spec parsing and validation."""

from __future__ import annotations

import json

import pytest

from xyberos_http_api import AuthSpec, HttpApiSpec, Operation, Param, RateLimitSpec, load_spec


def test_from_dict_minimal():
    spec = HttpApiSpec.from_dict(
        {
            "name": "weather",
            "base_url": "https://api.example.com/v1",
            "operations": [{"name": "ping", "method": "get", "path": "/ping"}],
        }
    )
    assert spec.name == "weather"
    assert spec.base_url == "https://api.example.com/v1"
    assert spec.operations[0].method == "GET"
    assert spec.timeout == 30.0
    assert spec.auth.type == "none"


def test_from_dict_full_operation():
    spec = HttpApiSpec.from_dict(
        {
            "name": "weather",
            "base_url": "https://api.example.com/v1/",
            "headers": {"Accept": "application/json"},
            "rate_limit": {"calls_per_second": 2, "burst": 3},
            "timeout": 5,
            "operations": [
                {
                    "name": "get_forecast",
                    "method": "GET",
                    "path": "/forecast",
                    "description": "Get the forecast",
                    "params": [
                        {"name": "latitude", "in": "query", "type": "number", "required": True},
                        {"name": "longitude", "in": "query", "type": "number", "required": True},
                        {"name": "units", "in": "query", "type": "string", "default": "metric"},
                        {"name": "id", "in": "path", "type": "string", "required": True},
                        {"name": "X-Trace", "in": "header", "type": "string"},
                        {"name": "payload", "in": "body", "type": "object"},
                    ],
                    "response_path": "current_weather.temperature",
                }
            ],
        }
    )
    assert spec.base_url == "https://api.example.com/v1"
    assert spec.headers == {"Accept": "application/json"}
    assert spec.rate_limit == RateLimitSpec(calls_per_second=2.0, burst=3)
    assert spec.timeout == 5.0
    op = spec.operations[0]
    assert isinstance(op, Operation)
    assert op.method == "GET"
    assert op.response_path == "current_weather.temperature"
    params = op.params
    assert params[0].python_type is float
    assert params[2].python_type is str
    assert params[2].default == "metric"
    assert params[3].in_ == "path"
    assert params[4].in_ == "header"
    assert params[5].in_ == "body"
    assert params[5].python_type is dict


def test_missing_name_and_base_url():
    with pytest.raises(ValueError, match="name"):
        HttpApiSpec.from_dict({"base_url": "https://x"})
    with pytest.raises(ValueError, match="base_url"):
        HttpApiSpec.from_dict({"name": "x"})


def test_operation_validation():
    with pytest.raises(ValueError, match="missing a 'name'"):
        HttpApiSpec.from_dict({"name": "x", "base_url": "https://x", "operations": [{"path": "/"}]})
    with pytest.raises(ValueError, match="unsupported method"):
        HttpApiSpec.from_dict(
            {"name": "x", "base_url": "https://x", "operations": [{"name": "a", "method": "FETCH"}]}
        )
    with pytest.raises(ValueError, match="bad 'in'"):
        HttpApiSpec.from_dict(
            {
                "name": "x",
                "base_url": "https://x",
                "operations": [
                    {"name": "a", "params": [{"name": "p", "in": "cookie"}]}
                ],
            }
        )


def test_load_spec_dict_and_list():
    spec = load_spec({"name": "a", "base_url": "https://a"})
    assert isinstance(spec, HttpApiSpec)
    specs = load_spec(
        [{"name": "a", "base_url": "https://a"}, {"name": "b", "base_url": "https://b"}]
    )
    assert isinstance(specs, list) and len(specs) == 2


def test_load_spec_json_file(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps({"name": "a", "base_url": "https://a", "operations": [{"name": "ping"}]}),
        encoding="utf-8",
    )
    spec = load_spec(str(path))
    assert spec.name == "a"
    assert spec.operations[0].name == "ping"


def test_load_spec_yaml_file(tmp_path):
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "api.yaml"
    path.write_text("name: a\nbase_url: https://a\noperations:\n  - name: ping\n", encoding="utf-8")
    spec = load_spec(path)
    assert spec.name == "a"
    assert spec.operations[0].name == "ping"


def test_load_spec_type_error():
    with pytest.raises(TypeError):
        load_spec(123)

"""Tests for loading the http_api plugin into a Xyberos app."""

from __future__ import annotations

import json

import pytest
from xyberos import create_app

from xyberos_http_api.plugin import HttpApiPlugin


def _spec_for(base_url: str) -> dict:
    return {
        "name": "demo",
        "base_url": base_url,
        "operations": [
            {
                "name": "get_user",
                "method": "GET",
                "path": "/users/{username}",
                "params": [{"name": "username", "in": "path", "required": True}],
            },
            {
                "name": "get_forecast",
                "method": "GET",
                "path": "/forecast",
                "params": [
                    {"name": "latitude", "in": "query", "type": "number", "required": True},
                    {"name": "longitude", "in": "query", "type": "number", "required": True},
                ],
            },
        ],
    }


def test_plugin_conforms_to_contract():
    plugin = HttpApiPlugin(_spec_for("https://example.com"))
    assert plugin.name == "http_api"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_plugin_registers_and_executes(server):
    base_url, _ = server
    app = create_app()
    plugin = HttpApiPlugin(_spec_for(base_url))
    app.load_plugin(plugin)

    assert "get_user" in app.tools.names
    assert "get_forecast" in app.tools.names

    result = app.tools.execute("get_user", None, username="baltz")
    assert result["login"] == "baltz"
    forecast = app.tools.execute("get_forecast", None, latitude="10.5", longitude="-66")
    assert forecast["latitude"] == 10.5

    app.unload_plugin(plugin.name)
    assert "get_user" not in app.tools.names


def test_plugin_from_json_file(server, tmp_path):
    base_url, _ = server
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_spec_for(base_url)), encoding="utf-8")
    app = create_app()
    app.load_plugin(HttpApiPlugin(path))
    assert "get_user" in app.tools.names


def test_plugin_from_env(server, monkeypatch):
    base_url, _ = server
    monkeypatch.setenv("HTTP_API_SPEC_JSON", json.dumps(_spec_for(base_url)))
    plugin = HttpApiPlugin()
    assert {t.name for t in plugin.tools()} == {"get_user", "get_forecast"}


def test_unconfigured_register_is_safe(server):
    base_url, _ = server
    app = create_app()
    plugin = HttpApiPlugin()  # no spec, no env
    app.load_plugin(plugin)  # must not raise
    assert app.plugins.names == ("http_api",)
    app.unload_plugin("http_api")


def test_multi_spec_tools_are_prefixed(server):
    base_url, _ = server
    specs = [_spec_for(base_url), {**_spec_for(base_url), "name": "second"}]
    plugin = HttpApiPlugin(specs)
    names = {t.name for t in plugin.tools()}
    assert "demo_get_user" in names
    assert "second_get_user" in names

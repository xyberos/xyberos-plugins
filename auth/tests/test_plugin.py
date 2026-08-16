"""Tests for loading the auth plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_auth import AuthPlugin


def test_plugin_conforms_to_contract():
    plugin = AuthPlugin()
    assert plugin.name == "auth"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_unconfigured_register_is_safe():
    app = create_app()
    app.load_plugin(AuthPlugin())  # no secret -> no-op
    assert app.plugins.names == ("auth",)
    app.unload_plugin("auth")


def test_plugin_registers_jwt_tools():
    app = create_app()
    app.load_plugin(AuthPlugin(secret="dev-secret"))
    assert "jwt_sign" in app.tools.names
    assert "jwt_verify" in app.tools.names

    token = app.tools.execute("jwt_sign", None, payload={"sub": "user-1"}, ttl=600)
    assert isinstance(token, str) and token.count(".") == 2

    claims = app.tools.execute("jwt_verify", None, token=token)
    assert claims["sub"] == "user-1"

    app.unload_plugin("auth")
    assert "jwt_sign" not in app.tools.names

"""M10 DoD: a trace lands in OTel / Langfuse from ``app.chat(...)``."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos import create_app

from xyberos_observability import LangfuseExporter, ObservabilityPlugin, OpenTelemetryExporter


def test_plugin_conforms_to_contract():
    plugin = ObservabilityPlugin()
    assert plugin.name == "observability"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_unconfigured_register_is_safe():
    app = create_app()
    app.load_plugin(ObservabilityPlugin())  # no exporters -> no-op
    assert app.plugins.names == ("observability",)
    app.unload_plugin("observability")


@pytest.mark.skipif(importlib.util.find_spec("opentelemetry") is None, reason="opentelemetry-sdk not installed")
def test_trace_lands_in_otel_from_chat():
    otel = OpenTelemetryExporter()
    app = create_app()
    app.load_plugin(ObservabilityPlugin(exporters=[otel]))

    app.chat("hello")  # the DoD: a trace lands in OTel from app.chat(...)

    app.unload_plugin("observability")
    names = [span.name for span in otel.spans()]
    assert any("request" in name for name in names)
    assert any("response" in name for name in names)


def test_trace_lands_in_langfuse_from_chat():
    sent: list[dict] = []

    def request(method, url, **kwargs):
        sent.append(kwargs["json_body"])
        return 200, {}

    langfuse = LangfuseExporter("pk", "sk", host="https://langfuse.example", request=request)
    app = create_app()
    app.load_plugin(ObservabilityPlugin(exporters=[langfuse]))

    app.chat("hello")

    app.unload_plugin("observability")
    assert sent, "expected at least one ingestion payload"
    names = {item["batch"][0]["name"] for item in sent}
    assert "brain.response_produced" in names


def test_unknown_exporter_raises(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_EXPORTERS", "bogus")
    with pytest.raises(ValueError, match="unknown exporter"):
        ObservabilityPlugin().exporters()

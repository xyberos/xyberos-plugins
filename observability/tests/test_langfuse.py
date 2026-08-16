"""Tests for the Langfuse exporter (injectable transport, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from xyberos.events import Event
from xyberos.exceptions.provider import ProviderError

from xyberos_observability import LangfuseExporter


def _fake_request(seen: dict):
    def request(method, url, **kwargs):
        seen.update({"url": url, "headers": kwargs["headers"], "payload": kwargs["json_body"]})
        return 200, {"success": True}

    return request


def test_export_sends_batch_item():
    seen: dict = {}
    exporter = LangfuseExporter("pk", "sk", host="https://langfuse.example", request=_fake_request(seen))
    exporter.export(
        Event(name="brain.response_produced", context=SimpleNamespace(prompt="hi"), data={"response": "hello"})
    )

    assert exporter.count == 1
    assert seen["url"] == "https://langfuse.example/api/public/ingestion"
    assert seen["headers"]["Authorization"].startswith("Basic ")
    batch = seen["payload"]["batch"]
    assert batch[0]["name"] == "brain.response_produced"
    assert batch[0]["input"] == "hi"
    assert batch[0]["output"] == {"response": "hello"}


def test_requires_keys():
    exporter = LangfuseExporter(public_key=None, secret_key=None, request=lambda *a, **k: (200, {}))
    with pytest.raises(ProviderError, match="LANGFUSE_PUBLIC_KEY"):
        exporter.export(Event(name="kernel.started"))

"""Tests for the Sentry exporter (injected capture/breadcrumb functions)."""

from __future__ import annotations

from xyberos.events import Event

from xyberos_observability import SentryExporter


def test_breadcrumb_and_capture():
    breadcrumbs: list[dict] = []
    captures: list[str] = []

    exporter = SentryExporter(
        add_breadcrumb=lambda b: breadcrumbs.append(b),
        capture_message=lambda m: captures.append(m),
    )
    exporter.export(Event(name="brain.response_produced", data={"response": "hello"}))
    exporter.export(Event(name="runtime.request_failed", data={"error": "boom"}))

    assert breadcrumbs[0]["message"] == "brain.response_produced"
    assert breadcrumbs[0]["data"] == {"response": "hello"}
    assert captures[0].startswith("Xyberos runtime.request_failed")

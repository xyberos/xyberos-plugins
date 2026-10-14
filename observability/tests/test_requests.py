"""The request span: the id the adapter minted, and the status the response got.

These tests go through the real adapter and its correlation middleware, which needs the runtime's
``http`` extra. They are skipped when it is absent, exactly as an application without that extra
has no HTTP surface to observe.
"""

from __future__ import annotations

import asyncio
import io
import logging

import pytest

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from xyberos import App
from xyberos.errors import HttpError

from xyberos_observability import (
    Observability,
    ObservabilitySettings,
    RequestSpanMiddleware,
    configure_logging,
)

pytest.importorskip("starlette", reason="the runtime's http extra provides the adapter")

from starlette.middleware import Middleware  # noqa: E402

from xyberos.http import HttpAdapter  # noqa: E402
from xyberos.http.testing import create_test_client  # noqa: E402

REQUEST_ID = "req-1"

#: The adapter's default is ``X-Request-ID``; it is named here and passed explicitly, so the test
#: asserts that the span reads whatever the adapter bound rather than a constant beside it.
REQUEST_ID_HEADER = "X-Request-ID"


def adapter(observability: Observability, app: App) -> HttpAdapter:
    """The one explicit wiring a composition root makes: the middleware, handed its tracer."""
    return HttpAdapter(
        app,
        request_id_header=REQUEST_ID_HEADER,
        middleware=[Middleware(RequestSpanMiddleware, tracer=observability.tracer)],
    )


def test_a_request_span_carries_the_correlation_id_the_adapter_minted() -> None:
    exporter = InMemorySpanExporter()
    observability = Observability(ObservabilitySettings(service="checkout"), exporter=exporter)

    async def read_order(order_id: int) -> dict[str, object]:
        return {"order": order_id}

    app = App()
    app.get("/orders/{order_id}")(read_order)
    try:
        with create_test_client(adapter(observability, app)) as client:
            response = client.get("/orders/7", headers={REQUEST_ID_HEADER: REQUEST_ID})
    finally:
        observability.shutdown()

    assert response.status_code == 200

    spans = exporter.get_finished_spans()
    assert len(spans) == 1, "one request is one span"
    span = spans[0]
    assert span.name == "GET /orders/7"
    assert span.kind is SpanKind.SERVER
    assert span.attributes["xyberos.correlation_id"] == REQUEST_ID
    assert span.attributes["http.request.method"] == "GET"
    assert span.attributes["url.path"] == "/orders/7"
    assert span.attributes["http.response.status_code"] == 200
    assert span.status.status_code is StatusCode.OK


def test_the_log_line_and_the_span_agree_on_the_correlation_id() -> None:
    stream = io.StringIO()
    exporter = InMemorySpanExporter()
    observability = Observability(ObservabilitySettings(service="checkout"), exporter=exporter)
    setup = configure_logging(
        ObservabilitySettings(level="INFO", logger="orders.api"), stream=stream
    )
    logger = logging.getLogger("orders.api")

    async def read_order(order_id: int) -> dict[str, object]:
        logger.info("looked up order %s", order_id)
        return {"order": order_id}

    app = App()
    app.get("/orders/{order_id}")(read_order)
    try:
        with create_test_client(adapter(observability, app)) as client:
            client.get("/orders/7", headers={REQUEST_ID_HEADER: REQUEST_ID})
    finally:
        setup.shutdown()
        observability.shutdown()

    assert stream.getvalue() == (
        f"INFO orders.api looked up order 7 {{'correlation_id': '{REQUEST_ID}'}}\n"
    )
    span = exporter.get_finished_spans()[0]
    assert span.attributes["xyberos.correlation_id"] == REQUEST_ID


def test_a_server_failure_is_an_error_and_a_client_mistake_is_not() -> None:
    exporter = InMemorySpanExporter()
    observability = Observability(ObservabilitySettings(service="checkout"), exporter=exporter)

    async def broken() -> dict[str, object]:
        raise RuntimeError("internal secret")

    async def gone() -> dict[str, object]:
        raise HttpError("order 9 is gone", status_code=410)

    app = App()
    app.get("/broken")(broken)
    app.get("/gone")(gone)
    try:
        with create_test_client(adapter(observability, app)) as client:
            assert client.get("/broken", headers={REQUEST_ID_HEADER: REQUEST_ID}).status_code == 500
            assert client.get("/gone", headers={REQUEST_ID_HEADER: REQUEST_ID}).status_code == 410
    finally:
        observability.shutdown()

    spans = {span.name: span for span in exporter.get_finished_spans()}
    failure = spans["GET /broken"]
    assert failure.attributes["http.response.status_code"] == 500
    assert failure.status.status_code is StatusCode.ERROR

    refusal = spans["GET /gone"]
    assert refusal.attributes["http.response.status_code"] == 410
    assert refusal.status.status_code is StatusCode.OK, "a client mistake is not a server fault"


def test_a_scope_that_is_not_http_is_passed_through_without_a_span() -> None:
    exporter = InMemorySpanExporter()
    observability = Observability(ObservabilitySettings(), exporter=exporter)
    seen: list[object] = []

    async def app(scope: dict[str, object], receive: object, send: object) -> None:
        seen.append(scope["type"])

    async def receive() -> dict[str, object]:
        return {}

    async def send(message: dict[str, object]) -> None:
        pass

    middleware = RequestSpanMiddleware(app, tracer=observability.tracer)
    asyncio.run(middleware({"type": "lifespan"}, receive, send))
    observability.shutdown()

    assert seen == ["lifespan"]
    assert exporter.get_finished_spans() == ()

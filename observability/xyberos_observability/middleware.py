"""One server span per request, keyed by the correlation id the adapter already minted.

``HttpAdapter`` builds its stack with the correlation middleware outermost, so by the time
application middleware runs, the runtime's context already carries the request's id — the same value
:class:`~xyberos.runtime.context.ContextLogFilter` puts on every log line. This middleware reads the
id from there and from nowhere else, which is exactly what makes a log line and a span agree.

It is a plain ASGI application rather than a Starlette middleware class, so this package does not
depend on the runtime's ``http`` extra; the application wires it explicitly, which also keeps the
order the application's own decision:

.. code-block:: python

    adapter = HttpAdapter(
        app,
        middleware=[Middleware(RequestSpanMiddleware, tracer=observability.tracer)],
    )

The span is named ``<method> <path>`` and carries ``http.request.method``, ``url.path``,
``http.response.status_code``, and ``xyberos.correlation_id``. The path is the raw one rather than
the route template, because the router has not matched yet at this point in the stack. A response of
500 or more is an error and a 4xx is not: a client that asked for something that is not there is
not a server fault.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, TypeAlias

from opentelemetry import context
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer, set_span_in_context
from opentelemetry.util.types import AttributeValue

from xyberos import get_correlation_id
from xyberos.errors import HttpError

from xyberos_observability.spans import CORRELATION_ID_ATTRIBUTE

__all__ = ["RequestSpanMiddleware"]

Scope: TypeAlias = MutableMapping[str, Any]
Message: TypeAlias = MutableMapping[str, Any]
Receive: TypeAlias = Callable[[], Awaitable[Message]]
Send: TypeAlias = Callable[[Message], Awaitable[None]]
ASGIApp: TypeAlias = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestSpanMiddleware:
    """Open one ``SERVER`` span per HTTP request, and pass every other scope through untouched."""

    def __init__(self, app: ASGIApp, *, tracer: Tracer) -> None:
        self._app = app
        self._tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        span = self._tracer.start_span(
            f"{method} {path}",
            kind=SpanKind.SERVER,
            attributes=_started_attributes(method, path),
        )
        status = 0

        async def send_tracked(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message.get("status", 0))
            await send(message)

        token = context.attach(set_span_in_context(span))
        try:
            await self._app(scope, receive, send_tracked)
        except BaseException as error:
            # The adapter's error middleware is outside this one, so a mapped failure arrives here as
            # the exception it was raised as, not as a response. The span reports the response the
            # adapter is about to send, by the same rule that middleware uses.
            code = status if status else _mapped_status(error)
            span.record_exception(error)
            span.set_attribute("http.response.status_code", code)
            span.set_status(Status(StatusCode.OK if code < 500 else StatusCode.ERROR))
            raise
        else:
            span.set_attribute("http.response.status_code", status)
            span.set_status(Status(StatusCode.OK if status < 500 else StatusCode.ERROR))
        finally:
            context.detach(token)
            span.end()


def _started_attributes(method: str, path: str) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {"http.request.method": method, "url.path": path}
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        attributes[CORRELATION_ID_ATTRIBUTE] = correlation_id
    return attributes


def _mapped_status(error: BaseException) -> int:
    """The status the adapter sends for this failure: an ``HttpError``'s own, otherwise 500."""
    if isinstance(error, HttpError):
        return error.status_code
    return 500

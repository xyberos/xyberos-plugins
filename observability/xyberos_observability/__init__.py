"""A logging handler and OpenTelemetry spans for Xyberos.

The runtime configures no logging and exports no telemetry of its own, and that is a promise rather
than an omission: a library that installs a handler fights the application that embeds it. This
package is the other half — one explicit call from the composition root that installs a handler, a
level, a format, and the runtime's own
:class:`~xyberos.runtime.context.ContextLogFilter`, and spans fed by the runtime's own event sink and
the correlation id the HTTP adapter already mints.

    from xyberos_observability import ObservabilitySettings, Observability

    observability = Observability(ObservabilitySettings(service="checkout"), exporter=exporter)
    observability.configure_logging()
    adapter = HttpAdapter(
        app, middleware=[Middleware(RequestSpanMiddleware, tracer=observability.tracer)]
    )
    await workflow.run(on_event=observability.event_sink())
    observability.shutdown()

What this package owns is the sink and the wiring: a handler, a tracer, a request span, and the
mapping from the runtime's events to spans. What it does not own is where the spans go — that is an
exporter the deployment passes — and it neither patches a runtime internal nor starts a thread.
"""

from xyberos_observability.logs import LoggingSetup, configure_logging
from xyberos_observability.middleware import RequestSpanMiddleware
from xyberos_observability.observability import Observability
from xyberos_observability.plugin import ObservabilityPlugin
from xyberos_observability.settings import DEFAULT_FORMAT, ObservabilitySettings
from xyberos_observability.spans import (
    CORRELATION_ID_ATTRIBUTE,
    EventSpans,
    step_span_name,
    workflow_span_name,
)

__all__ = [
    "CORRELATION_ID_ATTRIBUTE",
    "DEFAULT_FORMAT",
    "EventSpans",
    "LoggingSetup",
    "Observability",
    "ObservabilityPlugin",
    "ObservabilitySettings",
    "RequestSpanMiddleware",
    "configure_logging",
    "step_span_name",
    "workflow_span_name",
]

"""One object a composition root builds, configures, and shuts down.

Two things a running application has to be able to do with its telemetry: write it down where the
deployment collects it, and stop cleanly. Both are explicit here — a call that installs the logging
handler, a subscription the executor's events flow into, a middleware the adapter is handed, and one
``shutdown`` that gives all of it back.

Nothing is started at import, no global tracer provider is replaced, and no batch thread is spawned:
the runtime's events arrive on the execution path, so spans leave through ``SimpleSpanProcessor``. A
deployment that wants batching builds its own provider and passes it as ``tracer_provider``; one
that wants a collector passes an exporter, such as an OTLP one.
"""

from __future__ import annotations

from typing import IO

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

from xyberos import EventSink
from xyberos.errors import ConfigurationError

from xyberos_observability.logs import LoggingSetup, configure_logging
from xyberos_observability.settings import ObservabilitySettings
from xyberos_observability.spans import EventSpans

__all__ = ["Observability"]


class Observability:
    """A logging handler, a tracer, and the sinks that feed it.

    .. code-block:: python

        observability = Observability(ObservabilitySettings(service="checkout"))
        observability.configure_logging()  # one call: handler, level, format, context filter
        adapter = HttpAdapter(
            app,
            middleware=[Middleware(RequestSpanMiddleware, tracer=observability.tracer)],
        )
        await workflow.run(on_event=observability.event_sink())
        observability.shutdown()
    """

    settings: ObservabilitySettings
    """The settings this object was built with."""

    def __init__(
        self,
        settings: ObservabilitySettings | None = None,
        *,
        exporter: SpanExporter | None = None,
        tracer_provider: TracerProvider | None = None,
        stream: IO[str] | None = None,
    ) -> None:
        if exporter is not None and tracer_provider is not None:
            raise ConfigurationError(
                "pass an exporter or a tracer provider, not both: an exporter given beside a "
                "provider would be ignored, and a dropped telemetry sink is worse than a refusal"
            )
        self.settings = ObservabilitySettings() if settings is None else settings
        self._provider = (
            _build_provider(self.settings, exporter)
            if tracer_provider is None
            else tracer_provider
        )
        self._owns_provider = tracer_provider is None
        self._tracer = self._provider.get_tracer("xyberos_observability")
        self._stream = stream
        self._logging: LoggingSetup | None = None
        self._closed = False

    @property
    def tracer(self) -> Tracer:
        """The tracer every span this package opens is created from.

        Hand it to the request middleware, or use it for spans of the application's own.
        """
        return self._tracer

    @property
    def logging_setup(self) -> LoggingSetup | None:
        """The logging handle, once :meth:`configure_logging` has run."""
        return self._logging

    def configure_logging(self) -> LoggingSetup:
        """Install the handler, level, format, and context filter once, and return the handle."""
        if self._logging is None:
            self._logging = configure_logging(self.settings, stream=self._stream)
        return self._logging

    def event_sink(self) -> EventSink:
        """Return a fresh sink for one run: pass it to ``run(on_event=...)``.

        A sink owns the spans it opened and ``WorkflowEvent`` carries no run identifier, so one sink
        belongs to one run. Asking for a new one is the intended way to start another.
        """
        return EventSpans(self._tracer)

    def shutdown(self) -> None:
        """Remove the handler and shut the tracer provider down. Calling it twice is safe."""
        if self._closed:
            return
        self._closed = True
        setup, self._logging = self._logging, None
        if setup is not None:
            setup.shutdown()
        if self._owns_provider:
            self._provider.force_flush()
            self._provider.shutdown()


def _build_provider(settings: ObservabilitySettings, exporter: SpanExporter | None) -> TracerProvider:
    """Build the provider a deployment's spans leave through.

    Without an exporter the provider is still real — spans are created, timed, and statused — and
    they are dropped, which is the honest default for a package that must not open a socket the
    application did not ask for.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": settings.service}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider

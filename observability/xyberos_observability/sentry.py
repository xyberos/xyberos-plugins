"""Sentry exporter — breadcrumbs for events, captures for failures (lazy SDK).

The capture/breadcrumb functions are injectable so the mapping logic is fully
testable without ``sentry-sdk``; when not injected the SDK is imported lazily.
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable

from xyberos.events import BRAIN_ERROR, REQUEST_FAILED, Event
from xyberos.exceptions.provider import ProviderError

#: Callables injectable for tests (mirror sentry_sdk's add_breadcrumb/capture_message).
AddBreadcrumb = Callable[[dict[str, Any]], None]
CaptureMessage = Callable[[str], None]


class SentryExporter:
    """Adds a breadcrumb per event; captures failures as Sentry messages."""

    _FAILURE_EVENTS = {REQUEST_FAILED, BRAIN_ERROR}

    def __init__(
        self,
        *,
        dsn: str | None = None,
        add_breadcrumb: AddBreadcrumb | None = None,
        capture_message: CaptureMessage | None = None,
    ) -> None:
        self._dsn = dsn if dsn is not None else os.getenv("SENTRY_DSN")
        self._add_breadcrumb = add_breadcrumb
        self._capture_message = capture_message

    def export(self, event: Event) -> None:
        if event.name in self._FAILURE_EVENTS:
            self._capture(f"Xyberos {event.name}: {dict(event.data or {})}")
        else:
            self._breadcrumb(event)

    def __call__(self, event: Event) -> None:
        self.export(event)

    def _breadcrumb(self, event: Event) -> None:
        if self._add_breadcrumb is not None:
            self._add_breadcrumb(
                {"category": "xyberos.event", "message": event.name, "data": dict(event.data or {})}
            )
            return
        self._ensure_sdk()
        sentry_sdk.add_breadcrumb(category="xyberos.event", message=event.name, data=dict(event.data or {}))

    def _capture(self, message: str) -> None:
        if self._capture_message is not None:
            self._capture_message(message)
            return
        self._ensure_sdk()
        sentry_sdk.capture_message(message)

    def _ensure_sdk(self) -> None:
        global sentry_sdk  # noqa: PLW0603 - lazy module binding
        if "sentry_sdk" not in globals():
            try:
                sentry_sdk = importlib.import_module("sentry_sdk")
            except ImportError as exc:
                raise ProviderError(
                    "the 'sentry-sdk' package is required; install with "
                    "'pip install xyberos-observability[sentry]'"
                ) from exc
            globals()["sentry_sdk"] = sentry_sdk
            if self._dsn:
                sentry_sdk.init(dsn=self._dsn, traces_sample_rate=1.0)

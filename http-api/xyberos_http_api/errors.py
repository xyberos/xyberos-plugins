"""Errors raised by the HTTP/API connector."""

from __future__ import annotations


class HttpApiError(Exception):
    """Raised when an API request fails (non-2xx status or transport error).

    ``status`` is the HTTP status code (or ``None`` for transport errors) and
    ``body`` carries the raw response text when one was returned.
    """

    def __init__(self, status: int | None = None, body: str = "") -> None:
        self.status = status
        self.body = body
        message = f"HTTP {status}" if status is not None else "transport error"
        if body:
            message += f": {body[:200]}"
        super().__init__(message)

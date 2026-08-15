"""Shared fixtures for the http-api plugin tests.

Spins up a small ``http.server`` in a background thread so tests exercise the
full stdlib client without any external network.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class _Handler(BaseHTTPRequestHandler):
    # Class-level storage shared with the fixture.
    requests: list[dict[str, Any]] = []

    def log_message(self, *args: Any) -> None:  # silence
        pass

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body,
            }
        )

    def _json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self._record()
        from urllib.parse import parse_qs, urlparse

        path_only = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        if path_only.startswith("/users/"):
            name = path_only.rsplit("/", 1)[-1]
            self._json({"login": name, "public_repos": 42})
        elif path_only == "/forecast":
            self._json(
                {
                    "latitude": float(query.get("latitude", ["0"])[0]),
                    "longitude": float(query.get("longitude", ["0"])[0]),
                    "units": query.get("units", ["metric"])[0],
                    "current_weather": {"temperature": 21.5, "windspeed": 12.0},
                }
            )
        elif path_only == "/needs-key":
            if self.headers.get("X-API-Key") == "secret123":
                self._json({"ok": True})
            else:
                self._json({"error": "missing key"}, status=401)
        elif path_only == "/needs-bearer":
            if self.headers.get("Authorization") == "Bearer tok123":
                self._json({"ok": True})
            else:
                self._json({"error": "missing bearer"}, status=401)
        elif path_only == "/rate":
            self._json({"calls": len(self.__class__.requests)})
        elif path_only == "/missing":
            self._json({"error": "not found"}, status=404)
        else:
            self._json({"ok": True, "path": path_only})

    def do_POST(self) -> None:  # noqa: N802
        self._record()
        if self.path == "/echo":
            payload = json.loads(self._current_body())
            self._json({"echoed": payload})
        elif self.path == "/token":
            self._json({"access_token": "tok123", "expires_in": 3600})
        elif self.path == "/body":
            self._json({"received": json.loads(self._current_body())})
        else:
            self._json({"ok": True})

    def _current_body(self) -> str:
        record = self.__class__.requests[-1]
        return record["body"]


@pytest.fixture()
def server() -> Any:
    """Yield ``(base_url, requests)`` backed by a local HTTP server."""
    _Handler.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        yield base_url, _Handler.requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

"""A tiny stdlib HTTP helper (no third-party deps).

``default_request`` performs one HTTP request with ``urllib`` and returns
``(status, body)`` where ``body`` is parsed JSON when the response is JSON,
otherwise raw text. Injectable so tests run without a network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

#: (method, url, *, json_body, headers, query, timeout) -> (status, body)
RequestTransport = Callable[..., tuple[int, Any]]


def default_request(
    method: str,
    url: str,
    *,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    """Send one request and return ``(status, parsed_json_or_text)``."""
    final_url = url
    if query:
        separator = "&" if "?" in url else "?"
        final_url = url + separator + urllib.parse.urlencode(query)

    data: bytes | None = None
    request_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(
        final_url, data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")

    text = raw.decode("utf-8", errors="replace")
    if "application/json" in content_type or text.lstrip().startswith("{"):
        try:
            return 200, json.loads(text)
        except json.JSONDecodeError:
            return 200, text
    return 200, text

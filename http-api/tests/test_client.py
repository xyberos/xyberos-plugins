"""Tests for the stdlib HTTP client."""

from __future__ import annotations

import pytest

from xyberos_http_api import AuthSpec, HttpApiError, HttpClient, RateLimitSpec


def test_get_json(server):
    base_url, requests = server
    client = HttpClient(base_url)
    result = client.get("/forecast", query={"latitude": 10.5, "longitude": -66})
    assert result["latitude"] == 10.5
    assert requests[0]["method"] == "GET"
    assert "latitude=10.5" in requests[0]["path"]


def test_post_json_body(server):
    base_url, _ = server
    client = HttpClient(base_url)
    result = client.post("/body", body={"name": "x", "n": 3})
    assert result == {"received": {"name": "x", "n": 3}}


def test_http_error(server):
    base_url, _ = server
    client = HttpClient(base_url)
    with pytest.raises(HttpApiError) as exc_info:
        client.get("/missing")
    assert exc_info.value.status == 404


def test_bearer_header_sent(server):
    base_url, _ = server
    client = HttpClient(base_url, auth=AuthSpec(type="bearer", token="tok123"))
    assert client.get("/needs-bearer") == {"ok": True}


def test_api_key_header_sent(server):
    base_url, _ = server
    client = HttpClient(
        base_url, auth=AuthSpec(type="api_key", key_name="X-API-Key", value="secret123")
    )
    assert client.get("/needs-key") == {"ok": True}


def test_declared_headers_merged(server):
    base_url, requests = server
    client = HttpClient(base_url, headers={"X-Custom": "yes"})
    client.get("/users/baltz")
    assert requests[0]["headers"]["x-custom"] == "yes"


def test_rate_limiter_throttles(server):
    import time

    base_url, requests = server
    client = HttpClient(base_url, rate_limit=RateLimitSpec(calls_per_second=20, burst=1))
    start = time.monotonic()
    for _ in range(3):
        client.get("/rate")
    elapsed = time.monotonic() - start
    # 3 calls at 20/s with burst 1 => at least ~0.1s total.
    assert elapsed >= 0.09
    assert len(requests) == 3

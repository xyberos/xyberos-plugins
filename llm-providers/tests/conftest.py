"""Shared fixtures: a stub `post` transport that records requests.

All M6 adapters accept an injectable transport, so tests run with zero network.
``fake_post`` returns ``(post, seen)`` where ``seen`` collects every
``(url, payload, headers)`` triple.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def fake_post():
    seen: list[tuple[str, dict, dict]] = []

    def post(url: str, payload: dict, headers: dict) -> dict:
        seen.append((url, payload, headers))
        return {"choices": [{"message": {"content": "stub response"}}]}

    return post, seen

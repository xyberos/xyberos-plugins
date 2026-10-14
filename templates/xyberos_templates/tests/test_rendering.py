"""Escaping, the explicitly-safe case, and proof that a render does not hold the event loop.

These are ordinary pytest tests: a scenario that needs a loop is a synchronous test that calls
``asyncio.run(...)``, because this project has no pytest-asyncio.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

import pytest
from jinja2 import TemplateNotFound, select_autoescape
from markupsafe import Markup
from starlette.responses import HTMLResponse, Response

from xyberos_templates import Jinja2Templates, TemplatesSettings

#: What a page would carry if a value a user typed were ever rendered unescaped.
HOSTILE = "<script>alert(1)</script>"

#: A render that takes a real amount of time, expressed in seconds and in ticks of the loop.
PAUSE = 0.5
TICK = 0.01


def write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


def rendered(templates: Jinja2Templates, name: str, context: Mapping[str, object]) -> str:
    async def scenario() -> str:
        response = await templates.render(name, context)
        return response.body.decode()

    return asyncio.run(scenario())


@pytest.mark.parametrize("name", ["page.html", "page.j2"])
def test_a_value_is_escaped_whatever_the_template_is_called(tmp_path: Path, name: str) -> None:
    write(tmp_path, name, "<p>{{ value }}</p>")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    body = rendered(templates, name, {"value": HOSTILE})

    assert body == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
    assert HOSTILE not in body


def test_the_extension_policy_we_replace_is_the_one_that_leaves_a_j2_template_raw() -> None:
    """Why the policy is ours: the obvious helper is keyed on a file name, not on intent."""
    decide = select_autoescape()

    assert decide("page.html") is True
    assert decide("page.j2") is False, "this is the silent hole this package closes"


def test_markup_marked_safe_is_the_only_unescaped_output(tmp_path: Path) -> None:
    write(tmp_path, "marked.html", "{{ trusted }}")
    write(tmp_path, "filtered.html", "{{ trusted|safe }}")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    marked = rendered(templates, "marked.html", {"trusted": Markup("<b>bold</b>")})
    filtered = rendered(templates, "filtered.html", {"trusted": "<i>italic</i>"})

    assert marked == "<b>bold</b>"
    assert filtered == "<i>italic</i>"


def test_autoescape_can_be_turned_off_for_a_site_with_its_own_policy(tmp_path: Path) -> None:
    write(tmp_path, "page.html", "{{ value }}")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path, autoescape=False))

    assert rendered(templates, "page.html", {"value": HOSTILE}) == HOSTILE


def test_render_returns_the_response_it_was_asked_for(tmp_path: Path) -> None:
    write(tmp_path, "page.html", "<p>ok</p>")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    async def scenario() -> Response:
        return await templates.render(
            "page.html", {}, status_code=201, headers={"X-Page": "index"}
        )

    response = asyncio.run(scenario())

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 201
    assert response.headers["X-Page"] == "index"
    assert response.body == b"<p>ok</p>"


def test_a_missing_template_reports_its_name(tmp_path: Path) -> None:
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    async def scenario() -> None:
        await templates.render("missing.html", {})

    with pytest.raises(TemplateNotFound, match="missing.html"):
        asyncio.run(scenario())


def test_rendering_does_not_block_a_concurrent_coroutine(tmp_path: Path) -> None:
    """The measurement, not a mock: a coroutine sharing the loop must keep ticking.

    The template sleeps for ``PAUSE`` seconds, which releases the GIL, so a loop that is free ticks
    every ``TICK`` seconds and a loop that is held cannot tick at all.
    """
    write(tmp_path, "slow.html", "{{ pause(%s) }}" % PAUSE)
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))
    templates.environment.globals["pause"] = time.sleep

    async def scenario() -> tuple[float, int, str]:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(TICK)
                ticks += 1

        ticker = asyncio.create_task(tick())
        started = time.perf_counter()
        response = await templates.render("slow.html", {})
        elapsed = time.perf_counter() - started
        ticker.cancel()
        with suppress(asyncio.CancelledError):
            await ticker
        return elapsed, ticks, response.body.decode()

    elapsed, ticks, body = asyncio.run(scenario())

    assert body == "None", "the template really ran"
    assert elapsed >= PAUSE, "the render really took the time the template asked for"
    assert ticks >= 20, (
        "a coroutine sharing the loop keeps running while the template renders in a worker thread; "
        f"it only ticked {ticks} times out of at most {int(PAUSE / TICK)}"
    )


def test_the_async_path_runs_the_render_on_the_loop(tmp_path: Path) -> None:
    """The documented difference: ``render_async`` yields between awaits but saves no CPU time.

    Its CPU work happens where the loop can feel it, which is exactly why it is opt-in: a coroutine
    that asks to wait a fraction of the render waits for the whole render instead.
    """
    short_wait = PAUSE / 8
    write(tmp_path, "slow.html", "{{ burn() }}")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path, enable_async=True))

    async def burn() -> str:
        time.sleep(PAUSE)
        await asyncio.sleep(0)
        return "done"

    templates.environment.globals["burn"] = burn

    async def scenario() -> tuple[float, str]:
        async def wait_shortly() -> float:
            started = time.perf_counter()
            await asyncio.sleep(short_wait)
            return time.perf_counter() - started

        waiting = asyncio.create_task(wait_shortly())
        await asyncio.sleep(0)
        response = await templates.render("slow.html", {})
        return await waiting, response.body.decode()

    delayed, body = asyncio.run(scenario())

    assert body == "done", "the async path awaited the template's own awaitable"
    assert delayed >= PAUSE / 2, (
        f"a {short_wait:.3f}s wait took {delayed:.3f}s: render_async keeps the CPU work on the loop, "
        "where the off-loop path would have let the wait finish on time"
    )


def test_the_package_ships_its_types() -> None:
    marker = Path(__file__).resolve().parents[1] / "xyberos_templates" / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"

"""The shipped engine: Jinja2, rendered off the event loop, escaping on by default.

Two decisions here are the ones Starlette's ``Jinja2Templates`` does not make, and they are the
reason this package exists:

* A render runs in a worker thread through ``anyio.to_thread.run_sync(template.render, ...)``
  instead of inside ``TemplateResponse.__init__``, so a page that takes real CPU does not hold the
  event loop while it is produced. With ``enable_async`` set, the render goes through
  ``await template.render_async(...)`` instead, which is what a template that awaits something needs.
  The two paths are not interchangeable: ``render_async`` yields to the loop between its awaits but
  it does **not** move the CPU cost off the loop.
* ``autoescape`` is the boolean from the settings rather than ``select_autoescape()``, so a template
  named ``page.j2`` is escaped exactly like ``page.html``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path

import anyio
from jinja2 import Environment, FileSystemLoader
from starlette.applications import Starlette
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles

from xyberos_templates.settings import TemplatesSettings


class Jinja2Templates:
    """Render Jinja2 templates with the render cost off the event loop."""

    def __init__(self, settings: TemplatesSettings) -> None:
        self._settings = settings
        self._environment = Environment(
            loader=FileSystemLoader(str(settings.templates_directory)),
            autoescape=settings.autoescape,
            enable_async=settings.enable_async,
        )

    @property
    def settings(self) -> TemplatesSettings:
        """The validated settings this renderer was built from."""
        return self._settings

    @property
    def environment(self) -> Environment:
        """The Jinja environment, for registering filters and globals before the first render."""
        return self._environment

    async def render(
        self,
        name: str,
        context: Mapping[str, object],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Render ``name`` with ``context`` and return an HTML response.

        Loading and rendering both leave the event loop: the template is compiled in a worker
        thread and, unless ``enable_async`` is set, so is the render. With ``enable_async`` set the
        template runs on the loop through ``render_async``, which lets the template await its own
        context values at the cost of doing its CPU work where a request can feel it.
        """
        environment = self._environment
        template = await anyio.to_thread.run_sync(partial(environment.get_template, name))
        if self._settings.enable_async:
            body = await template.render_async(**context)
        else:
            body = await anyio.to_thread.run_sync(partial(template.render, **context))
        return HTMLResponse(body, status_code=status_code, headers=headers)

    def mount_static(
        self, app: Starlette, directory: str | Path, *, path: str | None = None
    ) -> str:
        """Serve ``directory`` from ``app`` at ``path``, or the settings' mount path."""
        mount_path = self._settings.static_path if path is None else path
        app.mount(mount_path, StaticFiles(directory=str(directory)), name="static")
        return mount_path

    async def read_form(self, request: Request) -> FormData:
        """Return the submitted form, multipart included."""
        return await request.form()

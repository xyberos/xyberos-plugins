"""The engine-neutral contract a page renderer satisfies.

Jinja2 is the engine this package ships, but nothing about a request handler needs to name it: a
handler depends on :class:`Templates`, and a team that would rather write typed components
implements the same members instead of forking this package. The members are the three things
serving pages needs and nothing else — render a named template, mount static files, read a
submitted form.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

from starlette.applications import Starlette
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response

from xyberos_templates.settings import TemplatesSettings


@runtime_checkable
class Templates(Protocol):
    """Render a named template, mount static files, and read a submitted form.

    ``render`` is a coroutine in the contract even for an engine that renders synchronously,
    because the seam exists so that the *implementation* decides where the work runs — a worker
    thread, the event loop, or somewhere else — and the caller cannot tell the difference.
    """

    @property
    def settings(self) -> TemplatesSettings:
        """The validated settings this renderer was built from."""
        ...

    async def render(
        self,
        name: str,
        context: Mapping[str, object],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """Render ``name`` with ``context`` and return the response to send."""
        ...

    def mount_static(
        self, app: Starlette, directory: str | Path, *, path: str | None = None
    ) -> str:
        """Serve ``directory`` from ``app`` at ``path``, or the settings' mount path.

        Returns the path it was mounted at, so a page can be handed the same value it links to.
        """
        ...

    async def read_form(self, request: Request) -> FormData:
        """Return the submitted form.

        Reading a multipart body needs ``python-multipart``, which this package declares so the
        assertion inside ``request.form()`` is never reached.
        """
        ...

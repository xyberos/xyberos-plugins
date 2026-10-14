"""Server-rendered pages for a Xyberos application, rendered off the event loop.

A handler depends on the contract, not on the engine:

    from starlette.requests import Request
    from starlette.responses import Response

    from xyberos_templates import Jinja2Templates, TemplatesSettings

    templates = Jinja2Templates(TemplatesSettings(directory="templates"))

    @app.get("/")
    async def index(request: Request) -> Response:
        return await templates.render("index.html", {"title": "Home"})

Two properties are the reason this package exists rather than ``starlette.templating.Jinja2Templates``:

* **The render does not run on the event loop.** Starlette's ``TemplateResponse`` renders
  synchronously inside ``__init__``, so the whole render cost lands on the loop. This package runs
  the render through ``anyio.to_thread.run_sync(template.render, ...)``, and switches to Jinja2's
  ``enable_async=True`` with ``await template.render_async(...)`` when a template itself awaits. The
  two are different: ``render_async`` yields to the loop between its awaits but does not reduce CPU
  time.
* **Autoescape is stated, not inherited.** ``select_autoescape()`` decides by file extension, so a
  template named ``page.j2`` is silently unescaped. Here escaping is on for every template, and the
  only unescaped output is markup that was marked safe on purpose.
"""

from xyberos_templates.contract import Templates
from xyberos_templates.jinja import Jinja2Templates
from xyberos_templates.settings import TemplatesSettings

__all__ = ["Jinja2Templates", "Templates", "TemplatesSettings"]

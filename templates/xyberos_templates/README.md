# xyberos-templates

**Server-rendered pages for a Xyberos application, with the render off the event loop and escaping
that is stated rather than inherited.**

`starlette.templating.Jinja2Templates` is nearly this, and the two places it is not are the whole
reason this package exists.

- **`TemplateResponse` renders synchronously inside `__init__`**, so the entire render cost lands on
  the event loop before any response bytes move. This package renders through
  `anyio.to_thread.run_sync(template.render, ...)`, and switches to Jinja2's `enable_async=True`
  with `await template.render_async(...)` when a template itself awaits. The two paths differ in a
  way worth knowing: `render_async` yields to the loop between its awaits, but it does **not** reduce
  CPU time — the render is still the loop's work.
- **`select_autoescape()` decides by file extension**, so a template named `page.j2` is silently
  unescaped while `page.html` is not. Autoescape here is a stated policy: every template is escaped,
  whatever it is called, and the only unescaped output is markup that was marked safe on purpose.

The seam is a `Protocol`, not a base class. A handler depends on `Templates`; Jinja2 is the engine
this package ships, and a team that would rather write typed components implements the same three
members instead of forking this package.

## Install

```bash
pip install xyberos-templates
```

## Register it

Settings are explicit, frozen, and validated where a bad value would otherwise fail on the first
request rather than at startup.

```python
from starlette.requests import Request
from starlette.responses import Response

from xyberos_templates import Jinja2Templates, TemplatesSettings

templates = Jinja2Templates(
    TemplatesSettings(directory="templates", static_path="/static")
)


@app.get("/")
async def index(request: Request) -> Response:
    return await templates.render("index.html", {"title": "Home"})
```

`directory`, `autoescape`, `enable_async`, and `static_path` are the whole of the configuration. New
filters and globals go on the Jinja environment those settings built:

```python
templates.environment.filters["money"] = format_money
```

The other two members of the contract are static files and forms:

```python
asgi_app = HttpAdapter(app).asgi_app
templates.mount_static(asgi_app, "static")  # returns "/static"


@app.post("/signup")
async def signup(request: Request) -> Response:
    form = await templates.read_form(request)  # python-multipart, declared by this package
    return await templates.render("thanks.html", {"email": form["email"]})
```

Rendering a template that itself awaits — an async callable in the context, say — needs
`enable_async=True`, which moves the render onto the loop on purpose:

```python
templates = Jinja2Templates(TemplatesSettings(directory="templates", enable_async=True))
```

## What it does not do

- **No caching layer.** Jinja2 compiles and caches templates itself. There is nothing above it, and
  no render cache keyed by template and context.
- **No second engine.** Jinja2 is the one engine shipped. Bringing another is implementing the
  `Templates` protocol, not configuring this package.
- **No asset pipeline.** `mount_static` serves a directory; hashing, bundling, and CDN URLs stay with
  the application.
- **No request-scoped helpers.** The context is exactly what the caller passes; nothing is injected
  behind its back.
- **No root key in `Settings`.** Settings are passed in, so nothing outside the application's own
  code decides where its pages come from.

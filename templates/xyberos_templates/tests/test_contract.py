"""The contract is usable by a second engine, and the other two members work end to end."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import FormData, UploadFile
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates as StarletteJinja2Templates

from xyberos import App
from xyberos.http import HttpAdapter
from xyberos.http.testing import create_test_client

from xyberos_templates import Jinja2Templates, Templates, TemplatesSettings


async def render_page(templates: Templates, name: str, context: Mapping[str, object]) -> Response:
    """Written against the contract: nothing here names an engine or a renderer."""
    return await templates.render(name, context)


def write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


class DictTemplates:
    """A second implementation with no engine at all, so the seam is not a Jinja2 wrapper."""

    def __init__(self, settings: TemplatesSettings, pages: Mapping[str, str]) -> None:
        self._settings = settings
        self._pages = dict(pages)

    @property
    def settings(self) -> TemplatesSettings:
        return self._settings

    async def render(
        self,
        name: str,
        context: Mapping[str, object],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        body = self._pages[name].format_map(context)
        return HTMLResponse(body, status_code=status_code, headers=headers)

    def mount_static(
        self, app: Starlette, directory: str | Path, *, path: str | None = None
    ) -> str:
        mount_path = self._settings.static_path if path is None else path
        app.mount(mount_path, StaticFiles(directory=str(directory)), name="static")
        return mount_path

    async def read_form(self, request: Request) -> FormData:
        return await request.form()


def test_a_hand_written_engine_satisfies_the_contract(tmp_path: Path) -> None:
    settings = TemplatesSettings(directory=tmp_path)
    templates: Templates = DictTemplates(settings, {"page.html": "hello {name}"})

    assert isinstance(templates, Templates), "the seam is structural, not a base class"

    async def scenario() -> str:
        response = await render_page(templates, "page.html", {"name": "world"})
        return response.body.decode()

    assert asyncio.run(scenario()) == "hello world"


def test_the_shipped_engine_renders_through_the_same_contract_function(tmp_path: Path) -> None:
    write(tmp_path, "page.html", "hello {{ name }}")
    templates: Templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    async def scenario() -> str:
        response = await render_page(templates, "page.html", {"name": "world"})
        return response.body.decode()

    assert asyncio.run(scenario()) == "hello world"


def test_the_shipped_engine_is_not_starlettes_renderer(tmp_path: Path) -> None:
    write(tmp_path, "page.html", "<p>ok</p>")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))

    assert StarletteJinja2Templates not in type(templates).__mro__, (
        "the render is this package's own"
    )
    assert not hasattr(templates, "TemplateResponse"), (
        "Starlette renders inside TemplateResponse.__init__; this package renders in render()"
    )


def test_static_files_are_mounted_through_the_contract(tmp_path: Path) -> None:
    static_directory = tmp_path / "static"
    static_directory.mkdir()
    (static_directory / "app.css").write_text("body{color:red}", encoding="utf-8")

    settings = TemplatesSettings(directory=tmp_path, static_path="/assets")
    templates: Templates = Jinja2Templates(settings)

    app = Starlette()
    mounted = templates.mount_static(app, static_directory)

    with create_test_client(app) as client:
        response = client.get(f"{mounted}/app.css")

    assert mounted == "/assets", "the settings' mount path is the default"
    assert response.status_code == 200
    assert response.text == "body{color:red}"


def test_a_submitted_form_is_read_through_the_xyberos_adapter(tmp_path: Path) -> None:
    write(tmp_path, "thanks.html", "thanks {{ email }}")
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))
    app = App()

    @app.post("/signup")
    async def signup(request: Request) -> Response:
        form = await templates.read_form(request)
        return await templates.render("thanks.html", {"email": form["email"]})

    with create_test_client(HttpAdapter(app)) as client:
        response = client.post("/signup", data={"email": "ada@example.com"})

    assert response.status_code == 200
    assert response.text == "thanks ada@example.com"


def test_a_multipart_form_is_read_because_python_multipart_is_declared(tmp_path: Path) -> None:
    templates = Jinja2Templates(TemplatesSettings(directory=tmp_path))
    app = App()

    @app.post("/upload")
    async def upload(request: Request) -> dict[str, str]:
        form = await templates.read_form(request)
        avatar = form["avatar"]
        return {
            "name": str(form["name"]),
            "file": avatar.filename if isinstance(avatar, UploadFile) else "",
        }

    with create_test_client(HttpAdapter(app)) as client:
        response = client.post(
            "/upload",
            data={"name": "Ada"},
            files={"avatar": ("ada.png", b"png-bytes", "image/png")},
        )

    assert response.status_code == 200
    assert response.json() == {"name": "Ada", "file": "ada.png"}

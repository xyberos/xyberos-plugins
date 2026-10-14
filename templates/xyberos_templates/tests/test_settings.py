"""Settings refuse a value that would fail later, naming the setting rather than the request."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyberos.errors import ConfigurationError

from xyberos_templates import TemplatesSettings


def test_the_defaults_state_our_own_policy(tmp_path: Path) -> None:
    settings = TemplatesSettings(directory=tmp_path)

    assert settings.autoescape is True, "escaping is on whatever the template is called"
    assert settings.enable_async is False, "the default render leaves the loop for a worker thread"
    assert settings.static_path == "/static"
    assert settings.templates_directory == tmp_path


def test_a_missing_directory_is_refused_here_rather_than_at_the_first_request(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigurationError, match="does not exist"):
        TemplatesSettings(directory=tmp_path / "missing")


def test_a_file_in_place_of_a_directory_is_refused(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "templates.html"
    not_a_directory.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="is not a directory"):
        TemplatesSettings(directory=not_a_directory)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"directory": ""}, "directory must not be empty"),
        ({"directory": "   "}, "directory must not be empty"),
        ({"static_path": ""}, "static_path must not be empty"),
        ({"static_path": "static"}, r"must start with '/'"),
        ({"static_path": "/"}, "must not be the site root"),
        ({"autoescape": "yes"}, "autoescape must be a bool"),
        ({"enable_async": 1}, "enable_async must be a bool"),
    ],
)
def test_settings_refuse_a_value_that_would_fail_later(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        TemplatesSettings(**{"directory": tmp_path, **changes})  # type: ignore[arg-type]

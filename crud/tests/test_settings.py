"""The bounds and the operator vocabulary, and every value that would fail later."""

from __future__ import annotations

from typing import Any

import pytest

from xyberos.errors import ConfigurationError
from xyberos_crud import CrudSettings
from xyberos_crud.settings import DEFAULT_OPERATORS, EQ, GTE, IS_NULL


def test_the_defaults_bound_a_page_and_allow_the_whole_vocabulary() -> None:
    settings = CrudSettings()

    assert settings.max_limit == 100
    assert settings.default_limit == 20
    assert settings.allowed_operators == DEFAULT_OPERATORS


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_limit": 0}, "max_limit must be positive"),
        ({"default_limit": 0}, "default_limit must be positive"),
        ({"max_limit": 5, "default_limit": 10}, "must not exceed max_limit"),
        ({"allowed_operators": frozenset[str]()}, "must name at least one operator"),
        ({"allowed_operators": frozenset({EQ, "regexp"})}, "unknown operator"),
    ],
)
def test_a_setting_that_would_fail_later_is_refused(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        CrudSettings(**changes)


def test_the_vocabulary_is_closed() -> None:
    """A name invented at a call site is refused where it is read, not at the database."""
    assert DEFAULT_OPERATORS == frozenset(
        {EQ, "ne", "lt", "lte", GTE, "gt", "in", "contains", "startswith", IS_NULL}
    )


def test_a_deployment_may_narrow_the_vocabulary() -> None:
    settings = CrudSettings(allowed_operators=frozenset({EQ}))

    assert settings.allowed_operators == frozenset({EQ})

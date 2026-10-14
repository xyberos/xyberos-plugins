"""Run the shipped conformance suite against this provider.

The core repository's ``packages.toml`` names this module as the package's conformance target, so
the compatibility job runs it against the published core, and this package's own CI runs it against
an OpenAI-compatible endpoint before a release is tagged. It exits non-zero when a check fails,
which is the point: a package that is installed and not checked is worse than one that is not
installed at all.

The endpoint is named by three variables, and the defaults describe the stub server this package's
tests ship — a real local HTTP service, so the suite exercises the wire format rather than a mock of
it. Claims are configuration: a deployment whose endpoint cannot do something turns that claim off
here, and the suite then checks that the provider *refuses* it instead of attempting it.
"""

from __future__ import annotations

import asyncio
import os
import sys

from xyberos.ai.testing import (
    assert_embedding_provider_contract,
    assert_model_provider_contract,
)

from xyberos_openai_compatible import OpenAICompatibleProvider, OpenAICompatibleSettings
from xyberos_openai_compatible.stub import running_stub

DEFAULT_BASE_URL = "http://127.0.0.1:59080/v1"
"""The address ``python -m xyberos_openai_compatible.stub`` binds, for a manual run. The
conformance target serves the same fake on an ephemeral port when nothing is configured, so this
default is what a reader sees rather than what the job uses."""

DEFAULT_MODEL = "stub-model"
DEFAULT_EMBEDDING_MODEL = "stub-embedding-model"

_TRUE = frozenset({"1", "true", "yes", "on"})


def _flag(value: str | None, *, default: bool) -> bool:
    """Read a boolean claim, falling back to the stub's own capabilities when it is unset."""
    if value is None:
        return default
    return value.strip().lower() in _TRUE


def _named(value: str | None, fallback: str) -> str:
    """Read a name, falling back when the variable is set but empty."""
    return value.strip() if value and value.strip() else fallback


def settings_from_environment(
    environment: dict[str, str] | None = None,
) -> OpenAICompatibleSettings:
    """Build settings from the environment this package's conformance target documents.

    ``XYBEROS_OPENAI_BASE_URL``, ``XYBEROS_OPENAI_API_KEY``, and ``XYBEROS_OPENAI_MODEL`` are the
    three a deployment must be able to state; the remaining variables turn capability claims off,
    because a claim is a promise the suite then holds the provider to.
    """
    source = os.environ if environment is None else environment
    return OpenAICompatibleSettings(
        model=_named(source.get("XYBEROS_OPENAI_MODEL"), DEFAULT_MODEL),
        base_url=_named(source.get("XYBEROS_OPENAI_BASE_URL"), DEFAULT_BASE_URL),
        api_key=source.get("XYBEROS_OPENAI_API_KEY", ""),
        embedding_model=_named(
            source.get("XYBEROS_OPENAI_EMBEDDING_MODEL"), DEFAULT_EMBEDDING_MODEL
        ),
        chat=_flag(source.get("XYBEROS_OPENAI_CHAT"), default=True),
        tools=_flag(source.get("XYBEROS_OPENAI_TOOLS"), default=True),
        structured_output=_flag(source.get("XYBEROS_OPENAI_STRUCTURED_OUTPUT"), default=True),
        streaming=_flag(source.get("XYBEROS_OPENAI_STREAMING"), default=True),
        embeddings=_flag(source.get("XYBEROS_OPENAI_EMBEDDINGS"), default=True),
    )


def main() -> int:
    """Run the suites, report what was checked, and return an exit code.

    With ``XYBEROS_OPENAI_BASE_URL`` set, the suites run against that deployment. Without it, the
    package serves the fake endpoint it ships on loopback and runs against that, so the conformance
    target proves the adapter with no infrastructure and no credential — which is what lets a job
    that holds no secrets run it at all. Claims are configuration either way: a deployment, or the
    fake, that cannot do something turns the claim off and the suite checks the refusal instead.
    """
    if _named(os.environ.get("XYBEROS_OPENAI_BASE_URL"), ""):
        return _run(settings_from_environment())
    with running_stub() as stub:
        return _run(settings_from_environment({"XYBEROS_OPENAI_BASE_URL": stub.base_url}))


def _run(settings: OpenAICompatibleSettings) -> int:
    """Run both suites against ``settings`` and report what was checked."""

    async def run() -> tuple[str, ...]:
        provider = OpenAICompatibleProvider(settings)
        try:
            checked = list(await assert_model_provider_contract(provider))
            # The embedding half is only claimed above, so the suite checks it against the endpoint
            # rather than checking a refusal.
            checked.extend(await assert_embedding_provider_contract(provider))
            return tuple(checked)
        finally:
            await provider.aclose()

    try:
        checked = asyncio.run(run())
    except AssertionError as error:
        print(f"failed: {error}")
        return 1
    for check in checked:
        print(f"ok: {check}")
    print(f"{len(checked)} checks passed against {settings.safe_base_url}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point the job runs
    sys.exit(main())

"""What this distribution answers for, checked rather than promised.

The package's surface is its promise: which names it exports, which it deliberately does not, and
what a reader is told about the break this release makes. Each of those is a test here, because a
name that comes back quietly is the failure this release exists to prevent.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import xyberos_mcp
from xyberos_mcp import protocol, server, tools

PACKAGE = Path(__file__).resolve().parents[1] / "xyberos_mcp"
README = Path(__file__).resolve().parents[1] / "README.md"

MODULES = (xyberos_mcp, protocol, server, tools)

CLIENT_SYMBOLS = frozenset(
    {
        "CLIENT_NAME",
        "McpCallResult",
        "McpClient",
        "McpServerInfo",
        "McpServerSettings",
        "McpToolInfo",
        "tools_for",
    }
)
"""The names the client half answers for. The client lives in the core package as ``xyberos.mcp``, so
none of them may appear here: one name answers one question."""


def _names(module: ModuleType) -> set[str]:
    """Return every name a module binds, other than private names and submodules."""
    return {
        name
        for name, value in vars(module).items()
        if not name.startswith("_") and not isinstance(value, ModuleType)
    }


def test_the_package_answers_for_no_client_symbol() -> None:
    for module in MODULES:
        names = _names(module)
        assert not (names & CLIENT_SYMBOLS), f"{module.__name__} exports a client symbol"

        clientish = sorted(name for name in names if "client" in name.lower())
        assert not clientish, f"{module.__name__} exports {clientish}"

        reached = sorted(
            name
            for name, value in vars(module).items()
            if isinstance(value, ModuleType) and value.__name__.startswith("xyberos.mcp")
        )
        assert not reached, f"{module.__name__} reaches for the client module: {reached}"


def test_the_package_answers_for_no_stdio_transport() -> None:
    """A stdio transport spawns a process, which is withheld until the project owner approves it."""
    for module in MODULES:
        stdio = sorted(name for name in _names(module) if "stdio" in name.lower())
        assert not stdio, f"{module.__name__} exports {stdio}"


def test_the_public_surface_is_exactly_what_the_package_declares() -> None:
    assert set(xyberos_mcp.__all__) == _names(xyberos_mcp)
    for name in xyberos_mcp.__all__:
        assert getattr(xyberos_mcp, name, None) is not None


def test_the_two_halves_of_the_seam_speak_one_protocol_version() -> None:
    from xyberos.mcp import SUPPORTED_PROTOCOL_VERSION as client_version

    assert xyberos_mcp.SUPPORTED_PROTOCOL_VERSION == client_version


def test_the_package_ships_its_types() -> None:
    marker = PACKAGE / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"
    assert marker.read_bytes() == b"", "the marker is a marker: the annotations are inline"


def test_the_readme_states_the_break_this_release_makes() -> None:
    """0.2.2 stays on the index unedited, so what did not come back has to be said before a reader
    misses it."""
    # Whitespace is collapsed because the claims are prose: a sentence that wrapped is still a claim.
    text = " ".join(README.read_text(encoding="utf-8").split()).lower()

    assert "0.2.2" in text, "the break is against the published version, and it is named"
    assert "xyberos.plugins" in text, "the entry point that does not return is named"
    assert "client lives in the core package" in text, "the client is core's, and the README says so"
    assert "stdio" in text and "withheld" in text, "the stdio transport is withheld, plainly"
    assert "0014" in text, "the authorization gap is ADR 0014's, and the README cites it"

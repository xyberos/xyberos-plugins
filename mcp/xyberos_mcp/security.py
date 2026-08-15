"""Security policies for MCP connections (RFC-0019, M3).

* No shell interpolation: stdio servers are launched with ``shell=False`` and a
  literal ``argv`` list, never a command string.
* Subprocess isolation: stdio servers run in a new session (POSIX) / hidden
  window (Windows) with an optional dedicated working directory.
* Allowlist: only explicitly configured servers may connect; a non-empty
  allowlist refuses anything else.
"""

from __future__ import annotations

from typing import Iterable

from .errors import McpSecurityError

#: Characters that only make sense to a shell; used as a defensive check on the
#: first token of a stdio command (the actual protection is ``shell=False``).
_SHELL_METACHARS = set("|&;<>`$(){}[]*?~#!\\\"")


def validate_command(argv: list[str]) -> list[str]:
    """Validate a stdio server command: a non-empty list of plain strings."""
    if not argv:
        raise McpSecurityError("stdio server command must be a non-empty list of strings")
    if not all(isinstance(token, str) for token in argv):
        raise McpSecurityError("stdio server command must contain only strings")
    if not argv[0].strip():
        raise McpSecurityError("stdio server command must name an executable")
    return list(argv)


def looks_shellish(argv: list[str]) -> bool:
    """True if the command contains obvious shell syntax (defensive check).

    ``subprocess.Popen(..., shell=False)`` already prevents shell
    interpretation; this is a belt-and-suspenders guard for misconfiguration.
    """
    return any(any(char in token for char in _SHELL_METACHARS) for token in argv)


class ServerAllowlist:
    """Restricts which servers may be connected by name."""

    def __init__(self, allowed: Iterable[str] | None = None) -> None:
        self._allowed = {str(name) for name in (allowed or ())}

    @property
    def empty(self) -> bool:
        return not self._allowed

    def check(self, name: str) -> None:
        if self._allowed and name not in self._allowed:
            raise McpSecurityError(
                f"server '{name}' is not in the MCP allowlist "
                f"(allowed: {sorted(self._allowed)})"
            )

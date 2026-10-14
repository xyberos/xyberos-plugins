"""What the distribution is, and what it deliberately is not.

These are the packaging half of the refusals in the README: this package ships its types, declares no
entry point, and has no module for the OAuth2 flows, the OIDC machinery, the presets, or a conformance
suite it does not own. The verification half lives in ``test_verifier.py`` and ``test_jwks.py``.
"""

from __future__ import annotations

from pathlib import Path

import xyberos_auth

PACKAGE_ROOT = Path(xyberos_auth.__file__).parent
DISTRIBUTION_ROOT = PACKAGE_ROOT.parent

#: Modules the published ``0.1.2`` had, and that this line does not: the flows, the discovery
#: machinery, the identity-provider presets, the plugin that registered them, and the conformance
#: module no shipped suite exists for.
REMOVED_MODULES = ("conformance", "errors", "http", "oauth2", "oidc", "plugin", "presets")


def test_the_package_declares_only_the_three_public_names() -> None:
    assert xyberos_auth.__all__ == ["AuthSettings", "Principal", "PrincipalVerifier"]


def test_the_modules_of_the_1x_line_are_gone() -> None:
    for name in REMOVED_MODULES:
        assert not (PACKAGE_ROOT / f"{name}.py").exists(), f"{name}.py is not part of this line"
        assert not (PACKAGE_ROOT / name).is_dir(), f"{name}/ is not part of this line"


def test_the_distribution_registers_nothing() -> None:
    """No entry point, no plugin object, no middleware: nothing loads this on an application's behalf."""
    pyproject = (DISTRIBUTION_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[project.entry-points" not in pyproject
    assert "xyberos.plugins" not in pyproject
    assert not hasattr(xyberos_auth, "plugin")
    assert not hasattr(xyberos_auth, "AuthPlugin")


def test_the_package_ships_its_types() -> None:
    assert (PACKAGE_ROOT / "py.typed").is_file(), "strict-mode consumers need the PEP 561 marker"


def test_cryptography_is_never_imported_at_module_level() -> None:
    """Every runtime import of it is inside a function, so a module load never needs it."""
    for module in sorted(PACKAGE_ROOT.glob("*.py")):
        for number, line in enumerate(module.read_text(encoding="utf-8").splitlines(), start=1):
            runtime_import = line.startswith("import ") or line.startswith("from ")
            if "cryptography" in line and runtime_import:
                raise AssertionError(
                    f"{module.name}:{number} imports cryptography when the module is loaded; it "
                    "belongs inside the function that builds or verifies a key"
                )

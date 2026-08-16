"""Example (M7): GitHub tools via the xyberos plugin.

Set GITHUB_TOKEN for authenticated calls (optional for public reads). Run:

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_github import GithubPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(GithubPlugin())

    user = app.tools.execute("github_get_user", None, username="octocat")
    print("user:", user["login"], "-", user["public_repos"], "public repos")

    repos = app.tools.execute("github_list_repos", None, username="octocat", per_page=3)
    for repo in repos:
        print("  -", repo["full_name"])

    app.unload_plugin("github")


if __name__ == "__main__":
    main()

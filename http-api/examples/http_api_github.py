"""Example (M2): point the HTTP/API connector at the GitHub REST API.

Works anonymously; set ``GITHUB_TOKEN`` for a higher rate limit.

    python examples/http_api_github.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_http_api import HttpApiPlugin


def main() -> None:
    spec_path = Path(__file__).resolve().parent / "github.json"
    app = create_app()
    app.load_plugin(HttpApiPlugin(spec_path))

    print("registered tools:", app.tools.names)
    print()
    print("get_user(username='octocat') →")
    user = app.tools.execute("get_user", None, username="octocat")
    print(" ", user.get("login"), "-", user.get("public_repos"), "public repos")

    print()
    print("list_repos(username='octocat', per_page=3) →")
    repos = app.tools.execute("list_repos", None, username="octocat", per_page=3)
    for repo in repos[:3]:
        print(" ", "-", repo.get("full_name"))

    app.unload_plugin("http_api")


if __name__ == "__main__":
    main()

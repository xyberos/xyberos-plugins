"""Example (M7): GitLab tools via the xyberos plugin. Requires GITLAB_TOKEN.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_gitlab import GitlabPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(GitlabPlugin())

    projects = app.tools.execute("gitlab_list_projects", None, search="xyberos", per_page=3)
    for project in projects:
        print("  -", project["path_with_namespace"])

    app.unload_plugin("gitlab")


if __name__ == "__main__":
    main()

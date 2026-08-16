"""Example (M7): Jira tools via the xyberos plugin.
Requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.

    python examples/example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_jira import JiraPlugin


def main() -> None:
    app = create_app()
    app.load_plugin(JiraPlugin())

    issues = app.tools.execute("jira_search_issues", None, jql="assignee = currentUser()", max_results=5)
    for issue in issues:
        print(f"  {issue['key']}: {issue['summary']} [{issue['status']}]")

    app.unload_plugin("jira")


if __name__ == "__main__":
    main()

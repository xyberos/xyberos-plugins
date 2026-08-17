# xyberos-slack

**Slack Web API plugin — RFC-0019, M7 (community wave).** Post messages and
list channels from Xyberos agents via the Slack Web API. Stdlib-only with an
injectable transport for tests.

## Install

```bash
pip install xyberos-slack              # from PyPI

# development (editable, from this repo):
pip install -e ./slack
```

## Usage

```python
from xyberos import create_app
from xyberos_slack import SlackPlugin

app = create_app()
app.load_plugin(SlackPlugin())              # token from SLACK_TOKEN

app.tools.execute("slack_post_message", None, channel="general", text="hello")
app.tools.execute("slack_list_channels", None, limit=100)
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `slack_post_message(channel, text)` | post to a channel |
| `slack_list_channels(limit=100)` | public channels |

Requires `SLACK_TOKEN` (a bot token with `chat:write` / `channels:read`).

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).

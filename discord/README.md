# xyberos-discord

**Discord bot API plugin — RFC-0019, M7 (community wave).** Send messages and
inspect channels from Xyberos agents via the Discord bot API (v10). Stdlib-only
with an injectable transport for tests.

## Install

```bash
pip install -e ./discord
```

## Usage

```python
from xyberos import create_app
from xyberos_discord import DiscordPlugin

app = create_app()
app.load_plugin(DiscordPlugin())          # token from DISCORD_TOKEN

app.tools.execute("discord_send_message", None, channel_id="111", content="hello")
app.tools.execute("discord_get_channel", None, channel_id="111")
```

## Tools

| Tool | Notes |
| ---- | ----- |
| `discord_send_message(channel_id, content)` | post a message |
| `discord_get_channel(channel_id)` | channel metadata |

Requires `DISCORD_TOKEN` (a bot token; auth sent as `Authorization: Bot ...`).

## Tests

```bash
pip install pytest
pytest tests/
```

Canned responses via an injectable transport — no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — community wave (M7).

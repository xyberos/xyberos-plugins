# xyberos-http-api

**Generic HTTP/API connector plugin — RFC-0019, M2.** *"Point at any REST API,
get typed tools."*

A declarative spec (JSON / YAML / Python `dict`) describes a `base_url`,
optional auth, optional rate limiting, and one *operation* per endpoint. Each
operation becomes a typed [`Tool`](https://docs.xyberos.com) whose parameters
are validated and coerced through `FunctionTool` / `coerce_arguments`.

This is the highest-leverage item after MCP: it is a dependency of the MCP
client (M3) and web search (M5), and it unblocks the whole multiplier chain.

## Install

```bash
pip install xyberos-http-api          # from PyPI

# development (editable, from this repo):
pip install -e ./http-api
```

## Usage

Load a plugin from a spec file:

```python
from xyberos import create_app
from xyberos_http_api import HttpApiPlugin

app = create_app()
app.load_plugin(HttpApiPlugin("examples/weather.json"))

app.tools.execute("get_forecast", None, latitude=40.71, longitude=-74.01)
```

Or from a `dict` / YAML, or configure it entirely through the environment:

```bash
export HTTP_API_SPEC=/path/to/spec.json     # or HTTP_API_SPEC_JSON='{...}'
```

The module-level `plugin` is auto-discovered via the `xyberos.plugins`
entry-point group; an unconfigured instance registers nothing (it logs a
warning instead of breaking `load_entry_points()`).

## Spec format

```jsonc
{
  "name": "github",
  "base_url": "https://api.github.com",
  "headers": { "Accept": "application/vnd.github+json" },
  "auth": { "type": "bearer", "token_env": "GITHUB_TOKEN" },
  "rate_limit": { "calls_per_second": 5, "burst": 10 },
  "operations": [
    {
      "name": "get_user",
      "method": "GET",
      "path": "/users/{username}",
      "description": "Get a GitHub user's public profile.",
      "params": [
        { "name": "username", "in": "path", "required": true },
        { "name": "per_page", "in": "query", "type": "integer", "default": 30 }
      ],
      "response_path": "some.nested[0].value"   // optional JSON extraction
    }
  ]
}
```

### Parameters

Each param has `name`, `in` (`query` | `path` | `header` | `body`), `type`
(`string` | `integer` | `number` | `boolean` | `array` | `object`),
`required`, `description`, and an optional `default`. The generated tool's JSON
schema mirrors these, so an LLM gets a typed signature.

### Auth

| type | fields | notes |
| ---- | ------ | ----- |
| `api_key` | `key_name`, `in` (`header`/`query`), `value`/`env` | sent per request |
| `bearer` | `token`/`token_env` | `Authorization: Bearer <token>` |
| `basic` | `username`/`username_env`, `password`/`password_env` | base64 basic |
| `oauth2` | `token_url`, `client_id`/`client_id_env`, `client_secret`/`client_secret_env`, `scope` | client_credentials, token cached |

Secrets are read from environment variables first, then literals. No secret is
ever required in the spec file.

### Rate limiting

`rate_limit` uses the core `xyberos.utils.resilience.RateLimiter` (token
bucket) and is applied per request.

## Examples

- `examples/http_api_weather.py` — Open-Meteo (no key).
- `examples/http_api_github.py` — GitHub REST API.

## Tests

```bash
pip install pytest
pytest tests/
```

The tests spin up a local `http.server` and exercise the full stdlib client —
no external network required.

## Contract & ship location

- **Contract:** `Tool` (`FunctionTool` public API only).
- **Ship:** Plugin (`xyberos.plugins` entry point).
- **Dependencies:** `xyberos>=1.0`; everything else is standard library.

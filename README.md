# Xyberos Plugins

Standalone integrations built against the Xyberos 2.x public contracts. Each
distribution is independently installable and composes providers explicitly;
these packages do not use the 1.x `xyberos.plugins` entry-point mechanism.

## Packages

| Distribution | Directory | Description |
| --- | --- | --- |
| `xyberos-auth` | [`auth/`](auth/) | Verification from a shared secret or JWKS, producing a `Principal` |
| `xyberos-crud` | [`crud/`](crud/) | Query construction for filtering, sorting, and pagination |
| `xyberos-knowledge` | [`knowledge/`](knowledge/) | Document chunking, embeddings, retrieval, and citations |
| `xyberos-memory` | [`memory/`](memory/) | Persistent conversation history and scoped facts over `DatabaseProvider` |
| `xyberos-mcp` | [`mcp/`](mcp/) | Exposes an application's tools over MCP |
| `xyberos-observability` | [`observability/`](observability/) | Logging setup and spans from the runtime event sink |
| `xyberos-openai-compatible` | [`llm-providers/xyberos_openai_compatible/`](llm-providers/xyberos_openai_compatible/) | `ModelProvider` for OpenAI-compatible endpoints |
| `xyberos-postgres` | [`db/xyberos_postgres/`](db/xyberos_postgres/) | `DatabaseProvider` for PostgreSQL |
| `xyberos-storage-s3` | [`storage/xyberos_storage_s3/`](storage/xyberos_storage_s3/) | `Storage` provider for S3-compatible object stores |
| `xyberos-templates` | [`templates/xyberos_templates/`](templates/xyberos_templates/) | Server-rendered pages with explicit autoescape behavior |

## Layout

A distribution lives in a directory of its own. Subjects with multiple
distributions group them under a shared folder, as with `db/`,
`llm-providers/`, `storage/`, and `templates/`. The publishing workflow
discovers distributions at both depths, and a tag names the distribution
directory (for example, `db/xyberos_postgres/v0.1.0`).

Type checking is per distribution. Each package declares its supported
`xyberos` range in its own `pyproject.toml`.

## Install & validate

Install the packages you need in the same environment:

```bash
pip install -e ./auth -e ./crud -e ./knowledge -e ./memory -e ./mcp
pip install -e ./observability
pip install -e ./llm-providers/xyberos_openai_compatible
pip install -e ./db/xyberos_postgres
pip install -e ./storage/xyberos_storage_s3
pip install -e ./templates/xyberos_templates

# run a package's tests from its directory
cd crud && python -m pytest tests -q
```

Each package has its own tests and README. Optional third-party dependencies
are imported lazily and report a clear error when they are required but missing.

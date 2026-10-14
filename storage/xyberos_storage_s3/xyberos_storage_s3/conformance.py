"""Run the shipped conformance suite against this provider.

The core repository's ``packages.toml`` names this module as the package's conformance target, so
the compatibility job runs it against the published core, and this package's own CI runs it against
an S3-compatible server before a release is tagged. It prints every check it ran and exits non-zero
when one fails, which is the point: a package that is installed and not checked is worse than one
that is not installed at all.

The server is named by ``XYBEROS_STORAGE_S3_*``; the defaults are a local S3-compatible server on
port 59000 with the credentials a ``docker run`` scratch instance is started with, which is what CI
starts a service container to serve.
"""

from __future__ import annotations

import asyncio
import os
import sys

from xyberos.storage.testing import assert_storage_contract

from xyberos_storage_s3 import S3StorageSettings, open_storage

DEFAULT_BUCKET = "xyberos-conformance"
"""A bucket of its own, so a conformance run never touches an application's objects."""

DEFAULT_ENDPOINT = "http://127.0.0.1:59000"
"""A local S3-compatible server, which is what CI starts a service container to serve."""

DEFAULT_REGION = "us-east-1"
DEFAULT_ACCESS_KEY = "minioadmin"
DEFAULT_SECRET_KEY = "minioadmin"


def settings_from_environment(environment: dict[str, str] | None = None) -> S3StorageSettings:
    """Build settings from ``XYBEROS_STORAGE_S3_*``.

    Six variables rather than a connection string, because an S3 client is configured by a bucket, an
    endpoint, a region, and a key pair — and the prefix, which is the one that lets a conformance run
    share a bucket with something else. A value the settings would refuse is refused here, before a
    server is contacted, which is why this raises rather than returning something unusable.
    """
    source = os.environ if environment is None else environment
    return S3StorageSettings(
        bucket=source.get("XYBEROS_STORAGE_S3_BUCKET", DEFAULT_BUCKET),
        endpoint_url=source.get("XYBEROS_STORAGE_S3_ENDPOINT", DEFAULT_ENDPOINT),
        region=source.get("XYBEROS_STORAGE_S3_REGION", DEFAULT_REGION),
        access_key=source.get("XYBEROS_STORAGE_S3_ACCESS_KEY", DEFAULT_ACCESS_KEY),
        secret_key=source.get("XYBEROS_STORAGE_S3_SECRET_KEY", DEFAULT_SECRET_KEY),
        prefix=source.get("XYBEROS_STORAGE_S3_PREFIX", ""),
    )


def main() -> int:
    """Run the suite, report what was checked, and return an exit code."""
    settings = settings_from_environment()

    async def run() -> tuple[str, ...]:
        storage = await open_storage(settings)
        try:
            return await assert_storage_contract(storage)
        finally:
            await storage.aclose()

    try:
        checked = asyncio.run(run())
    except Exception as error:  # noqa: BLE001 - a failed check is a report, not a traceback
        print(f"failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    for check in checked:
        print(f"ok: {check}")
    print(f"{len(checked)} checks passed against {settings.safe_endpoint}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point the job runs
    sys.exit(main())

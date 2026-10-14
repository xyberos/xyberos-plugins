"""What this provider promises without a server, and the suite it runs when there is one.

The tests are ordinary pytest tests: an async scenario is a synchronous test that calls
``asyncio.run(...)``. Everything here runs offline; the conformance suite needs a real S3-compatible
server and is skipped unless ``XYBEROS_STORAGE_S3_ENDPOINT`` names one
(``python -m xyberos_storage_s3.conformance`` runs it directly, which is what CI does against a
service container).
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from pathlib import Path

import pytest
from botocore.config import Config

from xyberos.errors import (
    StorageConfigurationError,
    StorageError,
    StorageKeyError,
    StorageSizeLimitError,
)
from xyberos.storage.testing import assert_storage_contract

from xyberos_storage_s3 import S3Storage, S3StorageSettings, open_storage, s3_storage
from xyberos_storage_s3.conformance import (
    DEFAULT_BUCKET,
    DEFAULT_ENDPOINT,
    settings_from_environment,
)

#: A port nothing listens on, so a refused connection is the fast, deterministic outcome.
DEAD_SERVER = S3StorageSettings(
    bucket="xyberos-tests",
    endpoint_url="http://127.0.0.1:1",
    access_key="conformance",
    secret_key="conformance",
    connect_timeout=1.0,
    read_timeout=1.0,
    retry_attempts=1,
)

LIVE_ENDPOINT = os.environ.get("XYBEROS_STORAGE_S3_ENDPOINT")


def test_the_secret_key_is_never_rendered() -> None:
    """A dataclass repr is the quickest way for a credential to reach a log."""
    settings = S3StorageSettings(
        bucket="reports",
        endpoint_url="https://s3.example.com",
        access_key="AKIAEXAMPLE",
        secret_key="s3cret",
    )

    assert "s3cret" not in repr(settings)
    assert "s3cret" not in settings.safe_endpoint
    assert settings.safe_endpoint == "https://s3.example.com/reports"


def test_a_prefix_namespaces_every_key_inside_the_bucket() -> None:
    plain = S3StorageSettings(bucket="reports", endpoint_url="https://s3.example.com")
    namespaced = S3StorageSettings(
        bucket="reports", endpoint_url="https://s3.example.com", prefix="app/data"
    )

    assert plain.key_prefix == ""
    assert namespaced.key_prefix == "app/data/"
    assert namespaced.safe_endpoint == "https://s3.example.com/reports/app/data"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"bucket": ""}, "bucket must not be empty"),
        ({"bucket": "Reports_Bucket"}, "is not a usable S3 bucket name"),
        ({"bucket": "ab"}, "is not a usable S3 bucket name"),
        ({"region": "us east 1"}, "is not a usable S3 region"),
        ({"region": "http://us-east-1"}, "is not a usable S3 region"),
        ({"endpoint_url": "s3.example.com:9000"}, "must be an http:// or https:// URL"),
        ({"endpoint_url": "http://"}, "must name a host"),
        ({"endpoint_url": "https://s3.example.com/?list=true"}, "must not carry a query"),
        ({"endpoint_url": "https://key:s3cret@s3.example.com"}, "must not carry credentials"),
        ({"access_key": "AKIAEXAMPLE", "secret_key": ""}, "must be set together"),
        ({"access_key": "", "secret_key": "s3cret"}, "must be set together"),
        ({"verify_tls": "/etc/ssl/certs/ca.pem"}, "verify_tls must be True or False"),
        ({"addressing_style": "reversed"}, "unsupported addressing_style"),
        ({"max_object_bytes": 0}, "max_object_bytes must be at least 1"),
        ({"max_key_length": 0}, "max_key_length must be at least 1"),
        ({"connect_timeout": -1.0}, "connect_timeout must be positive"),
        ({"read_timeout": 0.0}, "read_timeout must be positive"),
        ({"retry_attempts": 0}, "retry_attempts must be at least 1"),
        ({"prefix": "/leading"}, "prefix must be a usable storage key prefix"),
        ({"prefix": "a/../b"}, "prefix must be a usable storage key prefix"),
        ({"prefix": "a/.xyberos-hidden"}, "prefix must be a usable storage key prefix"),
    ],
)
def test_settings_refuse_a_value_that_would_fail_later(
    changes: dict[str, object], message: str
) -> None:
    arguments: dict[str, object] = {"bucket": "reports"}
    arguments.update(changes)

    with pytest.raises(StorageConfigurationError, match=message):
        S3StorageSettings(**arguments)  # type: ignore[arg-type]


def test_a_region_is_normalized_rather_than_rejected_for_its_case() -> None:
    assert S3StorageSettings(bucket="reports", region="US-East-1").region == "us-east-1"


def test_a_key_is_refused_before_any_network_call() -> None:
    storage = S3Storage(DEAD_SERVER)

    async def scenario() -> None:
        for bad_key in ("", "/absolute", "a/../escaped", "trailing/", "back\\slash", "\ncontrol"):
            with pytest.raises(StorageKeyError):
                await storage.put(bad_key, b"refused")
            with pytest.raises(StorageKeyError):
                await storage.get(bad_key)
            with pytest.raises(StorageKeyError):
                await storage.delete(bad_key)

        with pytest.raises(StorageKeyError):
            await storage.put(".xyberos-reserved/report.csv", b"refused")

    asyncio.run(scenario())


def test_text_is_refused_the_way_the_shipped_provider_refuses_it() -> None:
    storage = S3Storage(DEAD_SERVER)

    async def scenario() -> None:
        with pytest.raises(StorageError, match="holds bytes, not text"):
            await storage.put("reports/2026.csv", "text")  # type: ignore[arg-type]
        with pytest.raises(StorageError, match="stores bytes, and received int"):
            await storage.put("reports/2026.csv", 12)  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_an_object_over_the_ceiling_is_refused_before_any_network_call() -> None:
    storage = S3Storage(
        S3StorageSettings(bucket="xyberos-tests", endpoint_url="http://127.0.0.1:1", max_object_bytes=8)
    )

    async def scenario() -> None:
        with pytest.raises(StorageSizeLimitError, match="over this provider's 8-byte ceiling"):
            await storage.put("reports/2026.csv", b"012345678")

    assert storage.max_object_bytes == 8
    asyncio.run(scenario())


def test_an_unstarted_provider_reports_that_rather_than_connecting() -> None:
    storage = S3Storage(DEAD_SERVER)

    assert storage.max_object_bytes == DEAD_SERVER.max_object_bytes
    with pytest.raises(StorageError, match="has not been started"):
        _ = storage.client

    async def scenario() -> None:
        await storage.aclose()
        with pytest.raises(StorageError, match="has not been started"):
            await storage.put("reports/2026.csv", b"bytes")
        with pytest.raises(StorageError, match="has not been started"):
            await storage.get("reports/2026.csv")
        with pytest.raises(StorageError, match="has not been started"):
            await storage.delete("reports/2026.csv")
        with pytest.raises(StorageError, match="has not been started"):
            await storage.health()
        with pytest.raises(StorageError, match="has not been started"):
            _ = [key async for key in storage.list_keys()]
        await storage.aclose()

    asyncio.run(scenario())
    assert storage.settings is DEAD_SERVER


def test_a_refused_connection_is_a_storage_error_not_a_crash() -> None:
    async def scenario() -> None:
        with pytest.raises(StorageError, match="could not be opened"):
            await open_storage(DEAD_SERVER)

    asyncio.run(scenario())


def test_the_provider_factory_is_zero_argument_and_starts_the_storage() -> None:
    factory = s3_storage(DEAD_SERVER)

    async def scenario() -> None:
        with pytest.raises(StorageError):
            await factory()

    assert factory.__code__.co_argcount == 0
    asyncio.run(scenario())


def test_a_retry_budget_reaches_the_client_configuration() -> None:
    storage = S3Storage(
        S3StorageSettings(
            bucket="reports",
            endpoint_url="https://s3.example.com",
            access_key="AKIAEXAMPLE",
            secret_key="s3cret",
            region="eu-central-1",
            connect_timeout=2.5,
            read_timeout=7.5,
            retry_attempts=3,
            addressing_style="path",
        )
    )

    arguments = storage._client_arguments()  # pyright: ignore[reportPrivateUsage]
    config = arguments["config"]

    assert arguments["endpoint_url"] == "https://s3.example.com"
    assert arguments["region_name"] == "eu-central-1"
    assert arguments["verify"] is True
    assert arguments["aws_access_key_id"] == "AKIAEXAMPLE"
    assert isinstance(config, Config)
    assert config.connect_timeout == 2.5
    assert config.read_timeout == 7.5
    assert config.retries == {"max_attempts": 3, "mode": "standard"}
    assert config.s3 == {"addressing_style": "path"}


def test_credentials_left_empty_are_left_to_the_client_to_resolve() -> None:
    storage = S3Storage(S3StorageSettings(bucket="reports", endpoint_url="https://s3.example.com"))

    arguments = storage._client_arguments()  # pyright: ignore[reportPrivateUsage]

    assert "aws_access_key_id" not in arguments
    assert "aws_secret_access_key" not in arguments


def test_an_endpoint_outside_us_east_1_creates_a_bucket_where_it_says() -> None:
    storage = S3Storage(
        S3StorageSettings(
            bucket="reports", region="eu-central-1", endpoint_url="https://s3.example.com"
        )
    )
    plain = S3Storage(S3StorageSettings(bucket="reports", endpoint_url="https://s3.example.com"))

    assert storage._create_bucket_arguments() == {  # pyright: ignore[reportPrivateUsage]
        "CreateBucketConfiguration": {"LocationConstraint": "eu-central-1"}
    }
    assert plain._create_bucket_arguments() == {}  # pyright: ignore[reportPrivateUsage]


def test_the_conformance_module_reads_the_environment() -> None:
    settings = settings_from_environment(
        {
            "XYBEROS_STORAGE_S3_BUCKET": "reports",
            "XYBEROS_STORAGE_S3_ENDPOINT": "https://s3.example.com",
            "XYBEROS_STORAGE_S3_REGION": "eu-central-1",
            "XYBEROS_STORAGE_S3_ACCESS_KEY": "AKIAEXAMPLE",
            "XYBEROS_STORAGE_S3_SECRET_KEY": "s3cret",
            "XYBEROS_STORAGE_S3_PREFIX": "app",
        }
    )

    assert settings.bucket == "reports"
    assert settings.endpoint_url == "https://s3.example.com"
    assert settings.region == "eu-central-1"
    assert settings.access_key == "AKIAEXAMPLE"
    assert settings.secret_key == "s3cret"
    assert settings.prefix == "app"


def test_the_conformance_module_defaults_to_a_local_server() -> None:
    settings = settings_from_environment({})

    assert settings.bucket == DEFAULT_BUCKET
    assert settings.endpoint_url == DEFAULT_ENDPOINT
    assert settings.region == "us-east-1"
    assert settings.access_key == "minioadmin"
    assert settings.secret_key == "minioadmin"
    assert settings.prefix == ""


def test_the_conformance_module_refuses_a_server_it_cannot_use() -> None:
    with pytest.raises(StorageConfigurationError, match="endpoint_url must be an http"):
        settings_from_environment({"XYBEROS_STORAGE_S3_ENDPOINT": "127.0.0.1:59000"})


@pytest.mark.skipif(
    not LIVE_ENDPOINT,
    reason="set XYBEROS_STORAGE_S3_ENDPOINT to a scratch server to run the suite",
)
def test_the_shipped_suite_passes_against_a_real_server() -> None:
    async def scenario(settings: S3StorageSettings) -> tuple[str, ...]:
        storage = await open_storage(settings)
        try:
            return await assert_storage_contract(storage)
        finally:
            await storage.aclose()

    checked = asyncio.run(scenario(settings_from_environment()))
    assert len(checked) == 10, checked

    # The namespace is the one member the suite cannot exercise with default settings, so it runs a
    # second time behind a prefix: a bucket shared with another deployment must behave the same.
    prefixed = asyncio.run(
        scenario(dataclasses.replace(settings_from_environment(), prefix="conformance-namespace"))
    )
    assert len(prefixed) == 10, prefixed


def test_the_package_ships_its_types() -> None:
    marker = Path(__file__).resolve().parents[1] / "xyberos_storage_s3" / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"

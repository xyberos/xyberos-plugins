"""An S3-compatible object-storage provider, built on ``aioboto3``.

Three members of the contract need an S3 decision, and each is made here rather than inherited from
the shipped filesystem provider:

* ``list_keys`` asks the bucket for a prefix and filters the answer on the logical key, so the
  configured namespace never reaches a caller and the ascending order the contract promises is the
  order the bucket already returns (S3 lists keys in UTF-8 byte order, which is code-point order).
* ``delete`` asks whether the object was there before removing it, because S3 answers the removal of
  an absent key with the same success as the removal of one that is present, and the contract wants
  ``False`` for the first case.
* ``health`` publishes, reads back, and removes one probe object carrying the reserved segment
  prefix, so readiness reflects a bucket that can be written *and* read rather than one that merely
  answers a request.

The client is created by ``start`` and released by ``aclose``: a connection pool is a resource, and
the runtime closes a provider that exposes ``aclose`` because it is there.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, suppress
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urlsplit

# aioboto3 and botocore carry no PEP 561 marker, so a strict check calls them untyped: the ignore is
# about their packaging rather than an untyped call. Everything this module exposes is annotated, and
# the client is the one ``Any`` in it.
import aioboto3  # pyright: ignore[reportMissingTypeStubs]
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import BotoCoreError, ClientError  # pyright: ignore[reportMissingTypeStubs]

from xyberos.errors import (
    StorageConfigurationError,
    StorageError,
    StorageKeyError,
    StorageNotFoundError,
    StorageSizeLimitError,
)
from xyberos.storage.contracts import (
    DEFAULT_MAX_OBJECT_BYTES,
    MAX_KEY_LENGTH,
    RESERVED_SEGMENT_PREFIX,
    StoredObject,
    validate_key,
)

__all__ = ["S3Storage", "S3StorageSettings", "open_storage", "s3_storage"]

# A bucket name reaches DNS through virtual-host addressing, so a name the server would refuse is
# refused here instead: the alternative is a configuration that looks accepted and fails on the
# first upload, or on the first TLS handshake, with a message about a certificate.
_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

_REGION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

_ADDRESSING_STYLES = frozenset({"auto", "path", "virtual"})

#: The ways a server says "there is no object under that key": a modeled ``NoSuchKey`` from a GET,
#: and the bare ``404`` a HEAD is answered with, because a HEAD error carries no body to model.
_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})

#: The ways a server says "there is no such bucket".
_ABSENT_BUCKET_CODES = frozenset({"404", "NoSuchBucket", "NotFound"})

_HEALTH_PAYLOAD = b"xyberos-storage-health"

#: What the client raises when the server, the socket, or the deadline is the problem rather than
#: the request. Every one of them is a ``StorageError`` by the time it reaches a caller.
_CLIENT_FAILURES = (BotoCoreError, OSError, TimeoutError)

#: The same, plus the server's own refusal, which carries a code a decision can be made on.
_FAILURES = (ClientError, BotoCoreError, OSError, TimeoutError)


@dataclass(frozen=True)
class S3StorageSettings:
    """Explicit settings for :class:`S3Storage`.

    ``bucket`` is where objects live and ``prefix`` namespaces every key inside it, so two
    deployments can share one bucket without listing each other's objects. Nothing is trimmed,
    versioned, or encrypted: the provider writes the bytes it is given, under the key it is given,
    and the deployment owns the bucket's policy, its lifecycle rules, and its backup.

    Credentials are optional as a pair: left empty, the client resolves them from the environment,
    a profile, or an instance role, which is what a deployment on a cloud identity wants. They are
    never rendered — :attr:`safe_endpoint` is the one a log line or an error message should name.
    """

    bucket: str
    endpoint_url: str = "http://127.0.0.1:9000"
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = field(default="", repr=False)
    """Never rendered. A dataclass repr would put the credential into the first log line that
    prints the settings, and a log is the easiest place to lose a secret from."""
    prefix: str = ""
    """A namespace inside the bucket: every stored key is ``prefix/key`` and every listed key is
    reported without it, so a caller never sees the deployment's own layout. Empty means none."""
    verify_tls: bool = True
    addressing_style: str = "auto"
    create_bucket: bool = True
    max_object_bytes: int = DEFAULT_MAX_OBJECT_BYTES
    max_key_length: int = MAX_KEY_LENGTH
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    retry_attempts: int = 5

    def __post_init__(self) -> None:
        if not self.bucket:
            raise StorageConfigurationError("bucket must not be empty")
        if not _BUCKET_PATTERN.match(self.bucket):
            raise StorageConfigurationError(
                f"bucket {self.bucket!r} is not a usable S3 bucket name: 3-63 characters of "
                "lowercase letters, digits, dots and hyphens, starting and ending with a letter "
                "or digit"
            )
        self._check_endpoint()
        region = self.region.lower()
        if not _REGION_PATTERN.match(region):
            raise StorageConfigurationError(
                f"region {self.region!r} is not a usable S3 region: expected something like "
                "'us-east-1'"
            )
        object.__setattr__(self, "region", region)
        if bool(self.access_key) != bool(self.secret_key):
            raise StorageConfigurationError(
                "access_key and secret_key must be set together, or both left empty so the client "
                "resolves credentials from the environment, a profile, or an instance role"
            )
        if not isinstance(self.verify_tls, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            # The annotation says bool, and an untyped caller is exactly who this is for: a CA
            # bundle path is a non-empty string, and a non-empty string is truthy.
            raise StorageConfigurationError(
                "verify_tls must be True or False; a CA bundle path is not accepted here, because "
                "any non-empty string is truthy and would silently read as 'do not verify': "
                f"{self.verify_tls!r}"
            )
        if self.addressing_style not in _ADDRESSING_STYLES:
            supported = ", ".join(sorted(_ADDRESSING_STYLES))
            raise StorageConfigurationError(
                f"unsupported addressing_style {self.addressing_style!r}; expected one of: "
                f"{supported}"
            )
        if self.max_object_bytes < 1:
            raise StorageConfigurationError("max_object_bytes must be at least 1")
        if self.max_key_length < 1:
            raise StorageConfigurationError("max_key_length must be at least 1")
        if self.connect_timeout <= 0:
            raise StorageConfigurationError("connect_timeout must be positive")
        if self.read_timeout <= 0:
            raise StorageConfigurationError("read_timeout must be positive")
        if self.retry_attempts < 1:
            raise StorageConfigurationError("retry_attempts must be at least 1")
        if self.prefix:
            try:
                validate_key(self.prefix, max_length=self.max_key_length)
            except StorageKeyError as error:
                raise StorageConfigurationError(
                    f"prefix must be a usable storage key prefix: {error}"
                ) from error

    def _check_endpoint(self) -> None:
        """Refuse an endpoint that would fail at the first request, or leak a credential."""
        parts = urlsplit(self.endpoint_url)
        if parts.scheme not in {"http", "https"}:
            raise StorageConfigurationError(
                f"endpoint_url must be an http:// or https:// URL, not {self.endpoint_url!r}"
            )
        if not parts.netloc or not parts.hostname:
            raise StorageConfigurationError(
                f"endpoint_url must name a host, not {self.endpoint_url!r}"
            )
        if parts.query or parts.fragment:
            raise StorageConfigurationError(
                f"endpoint_url must not carry a query or a fragment: {self.endpoint_url!r}"
            )
        if parts.username is not None or parts.password is not None:
            raise StorageConfigurationError(
                "endpoint_url must not carry credentials: a URL is the first thing a log line or "
                "an error message prints, so pass access_key and secret_key instead of "
                f"{self.endpoint_url!r}"
            )

    @property
    def key_prefix(self) -> str:
        """The namespace every stored key carries, with its trailing ``/``.

        Empty when no prefix is configured, so ``key_prefix + key`` is the object name in the
        bucket without a conditional at the call site.
        """
        return f"{self.prefix}/" if self.prefix else ""

    @property
    def safe_endpoint(self) -> str:
        """Where this provider writes, without credentials, for a log line or an error message."""
        parts = urlsplit(self.endpoint_url)
        location = f"{parts.scheme}://{parts.netloc}"
        return f"{location}/{self.bucket}/{self.prefix}" if self.prefix else f"{location}/{self.bucket}"


class S3Storage:
    """Store objects in one S3-compatible bucket through one long-lived client."""

    def __init__(self, settings: S3StorageSettings) -> None:
        self.settings = settings
        self._stack: AsyncExitStack | None = None
        self._client: Any = None

    @property
    def max_object_bytes(self) -> int:
        """The largest object this provider accepts; ``put`` refuses anything larger."""
        return self.settings.max_object_bytes

    @property
    def client(self) -> Any:
        """Return the started client, or report that the provider was never started."""
        if self._client is None:
            raise StorageError("the storage has not been started")
        return self._client

    async def start(self) -> None:
        """Open the client and prove the bucket is usable before anyone is handed the provider.

        The bucket is created when it is missing and ``create_bucket`` allows it, and a missing
        bucket that the settings forbid creating is a configuration failure here rather than one
        discovered on the first upload.
        """
        if self._client is not None:
            return
        stack = AsyncExitStack()
        client: Any = None
        session: Any = aioboto3.Session()
        try:
            client = await stack.enter_async_context(
                cast(
                    AbstractAsyncContextManager[Any],
                    session.client("s3", **self._client_arguments()),
                )
            )
        except _CLIENT_FAILURES as error:
            await stack.aclose()
            raise StorageError(
                f"an S3 client for {self.settings.safe_endpoint} could not be created: {error}"
            ) from error
        except BaseException:
            # Including a cancellation: a client left behind holds connections the application can
            # no longer reach, and the caller is told the provider never started either way.
            await stack.aclose()
            raise
        self._stack, self._client = stack, client
        try:
            await self._ensure_bucket()
            await self.health()
        except _CLIENT_FAILURES as error:
            self._client = None
            self._stack = None
            await stack.aclose()
            raise StorageError(
                f"{self.settings.safe_endpoint} could not be opened: {error}"
            ) from error
        except BaseException:
            self._client = None
            self._stack = None
            await stack.aclose()
            raise

    async def aclose(self) -> None:
        """Release the client and its connections; closing an unstarted provider does nothing."""
        stack, self._stack = self._stack, None
        self._client = None
        if stack is not None:
            await stack.aclose()

    async def put(self, key: str, data: bytes) -> StoredObject:
        """Store ``data`` under ``key``, replacing what was there, and report what was stored."""
        if isinstance(data, str):
            raise StorageError(
                "storage holds bytes, not text: encode the payload first, for example "
                "data.encode('utf-8')"
            )
        if not isinstance(data, (bytes, bytearray, memoryview)):  # pyright: ignore[reportUnnecessaryIsInstance]
            # The annotation says bytes, and an untyped caller is exactly who this is for: a client
            # library would happily encode text into the body and store something the caller never
            # described.
            raise StorageError(f"put() stores bytes, and received {type(data).__name__}")
        validate_key(key, max_length=self.settings.max_key_length)
        payload = bytes(data)
        if len(payload) > self.settings.max_object_bytes:
            raise StorageSizeLimitError(
                f"{key!r} is {len(payload)} bytes, over this provider's "
                f"{self.settings.max_object_bytes}-byte ceiling"
            )
        try:
            await self.client.put_object(
                Bucket=self.settings.bucket, Key=self._object_key(key), Body=payload
            )
        except _FAILURES as error:
            raise StorageError(
                f"{key!r} could not be stored in {self.settings.safe_endpoint}: {error}"
            ) from error
        return StoredObject(key=key, size=len(payload))

    async def get(self, key: str) -> bytes:
        """Return the bytes stored under ``key``, or raise :class:`StorageNotFoundError`."""
        validate_key(key, max_length=self.settings.max_key_length)
        try:
            response = await self.client.get_object(
                Bucket=self.settings.bucket, Key=self._object_key(key)
            )
            async with response["Body"] as stream:
                return await stream.read()
        except ClientError as error:
            if _error_code(error) in _MISSING_CODES:
                raise StorageNotFoundError(f"no object is stored under {key!r}") from error
            raise StorageError(
                f"{key!r} could not be read from {self.settings.safe_endpoint}: {error}"
            ) from error
        except _CLIENT_FAILURES as error:
            raise StorageError(
                f"{key!r} could not be read from {self.settings.safe_endpoint}: {error}"
            ) from error

    async def delete(self, key: str) -> bool:
        """Remove ``key``, reporting whether an object was there.

        S3 answers the removal of an absent key with the same success as the removal of one that is
        present, so the provider asks whether the object exists first. That answer can be raced by a
        concurrent delete, which the contract's ``bool`` cannot express: a caller that needs a
        decision under concurrency needs a version, not this.
        """
        validate_key(key, max_length=self.settings.max_key_length)
        object_key = self._object_key(key)
        try:
            await self.client.head_object(Bucket=self.settings.bucket, Key=object_key)
        except ClientError as error:
            if _error_code(error) in _MISSING_CODES:
                return False
            raise StorageError(
                f"{key!r} could not be removed from {self.settings.safe_endpoint}: {error}"
            ) from error
        except _CLIENT_FAILURES as error:
            raise StorageError(
                f"{key!r} could not be removed from {self.settings.safe_endpoint}: {error}"
            ) from error
        try:
            await self.client.delete_object(Bucket=self.settings.bucket, Key=object_key)
        except _FAILURES as error:
            raise StorageError(
                f"{key!r} could not be removed from {self.settings.safe_endpoint}: {error}"
            ) from error
        return True

    async def list_keys(self, prefix: str = "") -> AsyncIterator[str]:
        """Yield the keys under ``prefix`` in ascending order.

        ``prefix`` is matched as a literal string, not as a directory: ``list_keys("a/b")`` also
        yields ``a/bc``. The bucket is asked for the namespaced prefix and the answer is filtered
        again on the logical key, so the configured namespace never reaches a caller. Keys a
        provider reserves for itself are never listed, and neither is the probe ``health`` uses.
        """
        namespace = self.settings.key_prefix
        paginator = self.client.get_paginator("list_objects_v2")
        try:
            async for page in paginator.paginate(
                Bucket=self.settings.bucket, Prefix=f"{namespace}{prefix}"
            ):
                for item in page.get("Contents", ()):
                    logical = str(item["Key"])[len(namespace) :]
                    if logical.startswith(prefix) and not _is_reserved(logical):
                        yield logical
        except _FAILURES as error:
            raise StorageError(
                f"keys under {prefix!r} could not be listed in {self.settings.safe_endpoint}: "
                f"{error}"
            ) from error

    async def health(self) -> None:
        """Probe the bucket by publishing, reading back, and removing one object.

        Answering a request is not enough: a bucket whose policy allows a read but not a write, or
        one whose credentials expired, still answers a listing. The probe carries the reserved
        segment prefix, so it can never collide with a stored key, and it is removed whether or not
        the read succeeded. A client the provider never opened is reported as such rather than
        dialled from here.
        """
        client = self.client
        probe = self._object_key(f"{RESERVED_SEGMENT_PREFIX}health")
        try:
            await client.put_object(
                Bucket=self.settings.bucket, Key=probe, Body=_HEALTH_PAYLOAD
            )
            response = await client.get_object(Bucket=self.settings.bucket, Key=probe)
            async with response["Body"] as stream:
                if await stream.read() != _HEALTH_PAYLOAD:
                    raise StorageError(
                        f"{self.settings.safe_endpoint} did not return what was written"
                    )
        except _FAILURES as error:
            raise StorageError(
                f"{self.settings.safe_endpoint} is not usable: {error}"
            ) from error
        finally:
            # Best-effort, and deliberately not awaited inside the except clause: a probe that
            # cannot be removed must not replace the failure that is being reported.
            with suppress(*_FAILURES):
                await client.delete_object(Bucket=self.settings.bucket, Key=probe)

    async def _ensure_bucket(self) -> None:
        """Make the bucket usable, or explain why it is not.

        ``create_bucket`` is the difference between a role that may materialise its own bucket and
        one that must find the bucket a template already made: with the setting off, a missing
        bucket is a configuration failure at startup rather than one discovered on the first
        upload.
        """
        try:
            await self.client.head_bucket(Bucket=self.settings.bucket)
            return
        except ClientError as error:
            if _error_code(error) not in _ABSENT_BUCKET_CODES:
                raise StorageError(
                    f"the bucket {self.settings.bucket!r} could not be reached at "
                    f"{self.settings.safe_endpoint}: {error}"
                ) from error
        if not self.settings.create_bucket:
            raise StorageConfigurationError(
                f"the bucket {self.settings.bucket!r} does not exist and create_bucket is false"
            )
        try:
            await self.client.create_bucket(
                Bucket=self.settings.bucket, **self._create_bucket_arguments()
            )
        except ClientError as error:
            # A second process may have created the bucket between the two calls, which is success.
            if _error_code(error) not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise StorageConfigurationError(
                    f"the bucket {self.settings.bucket!r} could not be created at "
                    f"{self.settings.safe_endpoint}: {error}"
                ) from error

    def _create_bucket_arguments(self) -> dict[str, Any]:
        """The ``CreateBucket`` arguments that depend on the region.

        Every region but ``us-east-1`` wants the location in the body, and ``us-east-1`` rejects it
        as an invalid constraint, so the argument is sent where it is right and not where a server
        would refuse a bucket creation for naming a region that is already implied.
        """
        if self.settings.region == "us-east-1":
            return {}
        return {"CreateBucketConfiguration": {"LocationConstraint": self.settings.region}}

    def _client_arguments(self) -> dict[str, Any]:
        """The arguments that open the client, including the retry budget and the deadlines."""
        arguments: dict[str, Any] = {
            "endpoint_url": self.settings.endpoint_url,
            "region_name": self.settings.region,
            "verify": self.settings.verify_tls,
            "config": Config(
                connect_timeout=self.settings.connect_timeout,
                read_timeout=self.settings.read_timeout,
                retries={
                    "max_attempts": self.settings.retry_attempts,
                    "mode": "standard",
                },
                s3={"addressing_style": self.settings.addressing_style},
            ),
        }
        if self.settings.access_key:
            arguments["aws_access_key_id"] = self.settings.access_key
            arguments["aws_secret_access_key"] = self.settings.secret_key
        return arguments

    def _object_key(self, key: str) -> str:
        """The name the object carries inside the bucket, with the configured namespace."""
        return f"{self.settings.key_prefix}{key}"


async def open_storage(settings: S3StorageSettings) -> S3Storage:
    """Create, start, and return a storage the caller owns and closes."""
    storage = S3Storage(settings)
    await storage.start()
    return storage


def s3_storage(settings: S3StorageSettings) -> Callable[[], Awaitable[S3Storage]]:
    """Return a zero-argument async factory, in the shape ``filesystem_storage`` already uses.

    The application owns configuration, so it composes the settings; the provider records them and
    hands ``app.provide(Storage, factory=s3_storage(settings), eager=True)`` the callable that opens
    the bucket. Nothing here reads the environment or a configuration file.
    """

    async def factory() -> S3Storage:
        return await open_storage(settings)

    return factory


def _error_code(error: ClientError) -> str:
    """The server's error code, which is what a decision is made on rather than the message."""
    response: dict[str, object] = error.response
    detail = response.get("Error")
    if isinstance(detail, dict):
        code = cast("dict[str, object]", detail).get("Code")
        if isinstance(code, str):
            return code
    return ""


def _is_reserved(key: str) -> bool:
    """Whether a stored key carries a segment a provider reserves for its own bookkeeping."""
    return any(segment.startswith(RESERVED_SEGMENT_PREFIX) for segment in key.split("/"))

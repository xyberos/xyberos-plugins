"""Object store adapters: S3, Azure Blob, GCS, OneDrive.

S3 / Azure / GCS lazy-import their SDK and accept an injectable client for
tests; OneDrive uses the Microsoft Graph REST API with an injectable transport.
"""

from __future__ import annotations

import os
from typing import Any

from xyberos.exceptions.provider import ProviderError

from .http import RequestTransport, default_request


class S3Store:
    """AWS S3 (lazy ``boto3``)."""

    name = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        client: Any | None = None,
        region: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = client
        self._region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")

    def list(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def upload(self, key: str, data: bytes) -> str:
        self._get_client().put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def download(self, key: str) -> bytes:
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError(
                "the 'boto3' package is required for S3; install with 'pip install xyberos-storage[s3]'"
            ) from exc
        kwargs = {"service_name": "s3"}
        if self._region:
            kwargs["region_name"] = self._region
        self._client = boto3.client(**kwargs)
        return self._client


class AzureBlobStore:
    """Azure Blob Storage (lazy ``azure-storage-blob``)."""

    name = "azure"

    def __init__(self, connection_string: str | None = None, *, container: str, client: Any | None = None) -> None:
        self._connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self._container = container
        self._client = client

    def _container_client(self) -> Any:
        if self._client is not None:
            return self._client.get_container_client(self._container)
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise ProviderError(
                "the 'azure-storage-blob' package is required; install with "
                "'pip install xyberos-storage[azure]'"
            ) from exc
        if not self._connection_string:
            raise ProviderError("Azure Blob requires AZURE_STORAGE_CONNECTION_STRING")
        return BlobServiceClient.from_connection_string(self._connection_string).get_container_client(self._container)

    def list(self, prefix: str = "") -> list[str]:
        container = self._container_client()
        return [blob.name for blob in container.list_blobs(name_starts_with=prefix)]

    def upload(self, key: str, data: bytes) -> str:
        self._container_client().upload_blob(key, data, overwrite=True)
        return key

    def download(self, key: str) -> bytes:
        blob = self._container_client().get_blob_client(key)
        return blob.download_blob().readall()


class GcsStore:
    """Google Cloud Storage (lazy ``google-cloud-storage``)."""

    name = "gcs"

    def __init__(self, bucket: str, *, client: Any | None = None) -> None:
        self._bucket = bucket
        self._client = client

    def _get_bucket(self) -> Any:
        if self._client is not None:
            return self._client.bucket(self._bucket)
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise ProviderError(
                "the 'google-cloud-storage' package is required; install with "
                "'pip install xyberos-storage[gcs]'"
            ) from exc
        return storage.Client().bucket(self._bucket)

    def list(self, prefix: str = "") -> list[str]:
        return [blob.name for blob in self._get_bucket().list_blobs(prefix=prefix)]

    def upload(self, key: str, data: bytes) -> str:
        blob = self._get_bucket().blob(key)
        blob.upload_from_string(data)
        return key

    def download(self, key: str) -> bytes:
        blob = self._get_bucket().blob(key)
        return blob.download_as_bytes()


class OneDriveStore:
    """Microsoft OneDrive via the Graph REST API (injectable transport)."""

    name = "onedrive"
    base_url = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        access_token: str | None = None,
        *,
        request: RequestTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._access_token = access_token if access_token is not None else os.getenv("ONEDRIVE_ACCESS_TOKEN")
        self._request = request or default_request
        self._timeout = timeout

    def list(self, prefix: str = "") -> list[str]:
        status, body = self._request(
            "GET",
            f"{self.base_url}/me/drive/root:{prefix}:/children",
            headers=self._headers(),
            timeout=self._timeout,
        )
        self._check(status, body)
        return [item.get("name") for item in body.get("value", [])]

    def upload(self, key: str, data: bytes) -> str:
        status, body = self._request(
            "PUT",
            f"{self.base_url}/me/drive/root:/{key}:/content",
            raw_body=data,
            headers=self._headers(),
            timeout=self._timeout,
        )
        self._check(status, body)
        return key

    def download(self, key: str) -> bytes:
        status, body = self._request(
            "GET",
            f"{self.base_url}/me/drive/root:/{key}:/content",
            headers=self._headers(),
            timeout=self._timeout,
        )
        self._check(status, body)
        return body.encode("utf-8") if isinstance(body, str) else body

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise ProviderError("OneDrive requires an access token (set ONEDRIVE_ACCESS_TOKEN)")
        return {"Authorization": f"Bearer {self._access_token}"}

    @staticmethod
    def _check(status: int, body: Any) -> None:
        if 200 <= status < 300:
            return
        message = body if isinstance(body, str) else str(body)
        raise ProviderError(f"OneDrive API returned HTTP {status}: {message[:200]}")

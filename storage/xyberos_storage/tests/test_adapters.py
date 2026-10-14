"""Tests for the object store adapters (fake clients / transports, no network)."""

from __future__ import annotations

import pytest
from xyberos.exceptions.provider import ProviderError

from xyberos_storage import AzureBlobStore, GcsStore, OneDriveStore, S3Store


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def get_paginator(self, _name):
        return self

    def paginate(self, **kwargs):
        prefix = kwargs.get("Prefix", "")
        return [
            {"Contents": [{"Key": key} for key in self.objects if key.startswith(prefix)]}
        ]

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {"Body": __import__("io").BytesIO(self.objects[kwargs["Key"]])}


def test_s3_roundtrip():
    client = _FakeS3Client()
    store = S3Store("bucket", client=client)
    store.upload("dir/a.txt", b"hello")
    assert store.list("dir/") == ["dir/a.txt"]
    assert store.download("dir/a.txt") == b"hello"


class _FakeStream:
    def __init__(self, data):
        self._data = data

    def readall(self):
        return self._data


class _FakeBlob:
    def __init__(self, name):
        self.name = name
        self.data = b""

    def download_blob(self):
        return _FakeStream(self.data)


class _FakeContainer:
    def __init__(self):
        self.blobs: dict[str, _FakeBlob] = {}

    def list_blobs(self, name_starts_with=""):
        return [b for name, b in self.blobs.items() if name.startswith(name_starts_with)]

    def upload_blob(self, name, data, **kwargs):
        blob = _FakeBlob(name)
        blob.data = data
        self.blobs[name] = blob

    def get_blob_client(self, name):
        return self.blobs[name]


class _FakeAzure:
    def get_container_client(self, _name):
        return self._container


def test_azure_roundtrip():
    container = _FakeContainer()
    service = _FakeAzure()
    service._container = container
    store = AzureBlobStore(container="c", client=service)
    store.upload("a.txt", b"hi")
    assert store.list() == ["a.txt"]
    assert store.download("a.txt") == b"hi"


def test_gcs_roundtrip():
    blobs: dict[str, bytes] = {}

    class _FakeBlobGcs:
        def __init__(self, name):
            self.name = name
            self._data = b""

        def upload_from_string(self, data):
            blobs[self.name] = data

        def download_as_bytes(self):
            return blobs[self.name]

    class _FakeBucket:
        def list_blobs(self, prefix=""):
            return [_FakeBlobGcs(name) for name in blobs if name.startswith(prefix)]

        def blob(self, name):
            if name not in blobs:
                blobs[name] = b""
            return _FakeBlobGcs(name)

    class _FakeGcsClient:
        def bucket(self, _name):
            return _FakeBucket()

    store = GcsStore("bucket", client=_FakeGcsClient())
    store.upload("k.txt", b"data")
    assert store.list() == ["k.txt"]
    assert store.download("k.txt") == b"data"


def test_onedrive_roundtrip():
    def request(method, url, **kwargs):
        if url.endswith(":/children"):
            return 200, {"value": [{"name": "a.txt"}]}
        if method == "PUT":
            return 201, {"name": "a.txt"}
        return 200, b"content"

    store = OneDriveStore(access_token="tok", request=request)
    assert store.list() == ["a.txt"]
    assert store.upload("a.txt", b"data") == "a.txt"
    assert store.download("a.txt") == b"content"


def test_onedrive_requires_token():
    store = OneDriveStore(access_token=None, request=lambda *a, **k: (200, {}))
    with pytest.raises(ProviderError, match="ONEDRIVE_ACCESS_TOKEN"):
        store.list()

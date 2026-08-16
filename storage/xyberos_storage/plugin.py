"""Storage plugin entry point (RFC-0019, M9)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import AzureBlobStore, GcsStore, OneDriveStore, S3Store
from .contract import ObjectStore
from .http import RequestTransport


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class StoragePlugin(Plugin):
    """Registers object-storage tools backed by a configured provider."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        env_prefix: str = "STORAGE",
        bucket: str | None = None,
        container: str | None = None,
        access_token: str | None = None,
        request: RequestTransport | None = None,
    ) -> None:
        self._provider = (provider or os.getenv(f"{env_prefix}_PROVIDER") or "s3").lower()
        self._bucket = bucket
        self._container = container or os.getenv(f"{env_prefix}_CONTAINER", "default")
        self._access_token = access_token
        self._request = request

    @property
    def name(self) -> str:
        return "storage"

    def object_store(self) -> ObjectStore:
        name = self._provider
        if name == "s3":
            bucket = self._bucket or os.getenv("STORAGE_BUCKET") or os.getenv("S3_BUCKET")
            if not bucket:
                raise ValueError("s3 provider requires a bucket (STORAGE_BUCKET)")
            return S3Store(bucket)
        if name == "azure":
            return AzureBlobStore(container=self._container)
        if name == "gcs":
            bucket = self._bucket or os.getenv("STORAGE_BUCKET") or os.getenv("GCS_BUCKET")
            if not bucket:
                raise ValueError("gcs provider requires a bucket (STORAGE_BUCKET)")
            return GcsStore(bucket)
        if name == "onedrive":
            return OneDriveStore(self._access_token, request=self._request)
        raise ValueError(f"unknown storage provider '{name}' (s3 | azure | gcs | onedrive)")

    def tools(self) -> list[Tool]:
        store = self.object_store()

        def _list(prefix: str = "") -> list[str]:
            return store.list(prefix)

        def _upload(key: str, file_path: str) -> str:
            data = Path(file_path).read_bytes()
            return store.upload(key, data)

        def _download(key: str, output_path: str) -> str:
            data = store.download(key)
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return str(path)

        return [
            FunctionTool("storage_list", _list, description=f"List objects via {self._provider}."),
            FunctionTool("storage_upload", _upload, description=f"Upload a file to {self._provider}."),
            FunctionTool("storage_download", _download, description=f"Download an object from {self._provider}."),
        ]

    def register(self, kernel: object) -> None:
        try:
            tools = self.tools()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("storage plugin not configured: %s", exc)
            return
        registry = kernel.resolve("tools")
        for tool in tools:
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        try:
            tools = self.tools()
        except ValueError:
            return  # never configured -> nothing was registered
        registry = kernel.resolve("tools")
        for tool in tools:
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = StoragePlugin()

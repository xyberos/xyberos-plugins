"""Object storage plugin (RFC-0019, M9)."""

from .adapters import AzureBlobStore, GcsStore, OneDriveStore, S3Store
from .contract import ObjectStore
from .plugin import StoragePlugin

__all__ = ["AzureBlobStore", "GcsStore", "ObjectStore", "OneDriveStore", "S3Store", "StoragePlugin"]

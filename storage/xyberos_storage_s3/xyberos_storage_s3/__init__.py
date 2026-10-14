"""S3-compatible object storage as a Xyberos ``Storage`` provider.

Services depend on :class:`~xyberos.storage.contracts.Storage`, never on this package: the provider
is supplied at composition time, already started, and the application owns closing it.

    from xyberos import App
    from xyberos.storage import Storage
    from xyberos_storage_s3 import S3StorageSettings, s3_storage

    app = App()
    app.provide(Storage, factory=s3_storage(S3StorageSettings(...)), eager=True)

What this package owns is the client, the bucket, and the two S3-specific members of the contract:
keys are listed by asking the bucket for a prefix and filtering the answer, so the stored key order
stays the bucket's own ascending order, and a delete has to ask whether the object was there,
because S3 answers the removal of an absent key with the same success as the removal of one that is
present. What it does not own is anything the contract is silent about — versions, multipart
uploads, content types, signed URLs, bucket policy.
"""

from xyberos_storage_s3.provider import (
    S3Storage,
    S3StorageSettings,
    open_storage,
    s3_storage,
)

__all__ = ["S3Storage", "S3StorageSettings", "open_storage", "s3_storage"]

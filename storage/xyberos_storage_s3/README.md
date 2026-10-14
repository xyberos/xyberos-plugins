# xyberos-storage-s3

**A `Storage` provider for S3-compatible object stores, proved against the suite this project ships.**

Xyberos keeps one storage provider in the core (`xyberos.storage`, local filesystem) and makes the
boundary a protocol: a service depends on `Storage`, never on a client library. This package supplies
a second implementation — `aioboto3` against any S3-compatible endpoint, which is AWS S3, MinIO,
Ceph RGW, Cloudflare R2 or Backblaze B2 — and proves it the way
[`docs/storage.md`](https://github.com/xyberos/xyberos2.0/blob/master/docs/storage.md) requires, by
running the shipped conformance suite against a real server rather than by asserting that it works.

## Install

```bash
pip install xyberos-storage-s3

# development (editable, from this repo):
pip install -e ./storage/xyberos_storage_s3
```

## Register it

A provider arrives the way any other service does: already started, supplied as an instance the
application owns and closes.

```python
from xyberos import App
from xyberos.storage import Storage
from xyberos_storage_s3 import S3StorageSettings, s3_storage

app = App()
app.provide(
    Storage,
    factory=s3_storage(
        S3StorageSettings(
            bucket="xyberos-reports",
            endpoint_url="https://s3.eu-central-1.amazonaws.com",
            region="eu-central-1",
            access_key="******",
            secret_key="******",
            prefix="checkout",
        )
    ),
    eager=True,
)
```

The settings carry the bucket, the endpoint, the region, the credentials, the namespace `prefix`, the
TLS switch, the two deadlines, and the retry budget. The secret is never rendered: `safe_endpoint` is
the one a log line or an error message should name. `start()` proves the bucket can be written *and*
read — and creates it when `create_bucket` allows that — so a mistyped endpoint is a startup failure
rather than a 500 on the first upload, and `aclose()` releases the client, which the runtime closes
because it is there.

Two settings are worth naming:

- **`prefix`** namespaces every key inside the bucket: a caller stores `reports/2026-q1.csv`, the
  bucket holds `checkout/reports/2026-q1.csv`, and a listing hands back `reports/2026-q1.csv`. Two
  deployments can share one bucket without listing each other's objects.
- **Credentials left empty** are resolved by the client from the environment, a profile, or an
  instance role, which is what a deployment on a cloud identity wants. `verify_tls` is a boolean and
  not a CA bundle path, because a path is a non-empty string and a non-empty string is truthy.

## Conformance

```bash
XYBEROS_STORAGE_S3_ENDPOINT=http://127.0.0.1:59000 \
  python -m xyberos_storage_s3.conformance
```

The core repository's `packages.toml` names that module as this package's conformance target, so the
compatibility job runs it against the published core, and a release waits on it passing against an
S3-compatible service. It reads `XYBEROS_STORAGE_S3_BUCKET`, `..._ENDPOINT`, `..._REGION`,
`..._ACCESS_KEY`, `..._SECRET_KEY` and `..._PREFIX`, defaulting to a local scratch server on port
59000, the bucket `xyberos-conformance`, and `minioadmin` credentials. It prints every check and exits
non-zero on the first failure, including one that is only a refused connection.

## What it does not do

- **No multipart uploads.** One `put` is one `PutObject`, which is why the 64 MiB default ceiling sits
  far below the 5 GiB a single request could carry: an object past it is refused, not split.
- **No versioning, signed URLs, or content types.** The contract is an opaque payload under a key, and
  a provider that smuggled a backend-specific API into application code would defeat the point of it.
- **No server-side encryption, lifecycle rules, or bucket policy.** Those belong to the bucket, which
  the deployment owns, and to the infrastructure that creates it.
- **No transient-error marker.** The core ships no storage error that is also a `TransientError`, so a
  failure a retry policy might want to retry arrives as a plain `StorageError`; the retry decision is
  the caller's, and the client's own retry budget is what `retry_attempts` configures.

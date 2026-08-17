# xyberos-storage

**Object storage plugin — RFC-0019, M9.** S3, Azure Blob, GCS, and OneDrive
behind one `ObjectStore` contract (`list` / `upload` / `download`).

## Install

```bash
pip install xyberos-storage            # from PyPI
pip install xyberos-storage[s3]        # optional: boto3
pip install xyberos-storage[azure]     # optional: azure-storage-blob
pip install xyberos-storage[gcs]       # optional: google-cloud-storage

# development (editable, from this repo):
pip install -e ./storage
```

## Usage

```python
from xyberos import create_app
from xyberos_storage import StoragePlugin

app = create_app()
app.load_plugin(StoragePlugin(provider="s3", bucket="my-bucket"))  # or STORAGE_PROVIDER

app.tools.execute("storage_list", None, prefix="data/")
app.tools.execute("storage_upload", None, key="data/x.txt", file_path="x.txt")
app.tools.execute("storage_download", None, key="data/x.txt", output_path="out.txt")
```

| Provider | Key / config |
| -------- | ------------ |
| `s3` | `STORAGE_BUCKET` + AWS creds (lazy boto3) |
| `azure` | `AZURE_STORAGE_CONNECTION_STRING` + `STORAGE_CONTAINER` (lazy SDK) |
| `gcs` | `STORAGE_BUCKET` + GCP creds (lazy SDK) |
| `onedrive` | `ONEDRIVE_ACCESS_TOKEN` (Graph REST) |

## Tools

- `storage_list(prefix="")`
- `storage_upload(key, file_path)`
- `storage_download(key, output_path)`

## Tests

```bash
pip install pytest
pytest tests/
```

Fake clients / injectable transports — no cloud, no network.

## Ship location

Plugin (`xyberos.plugins` entry point) — enterprise storage (M9).

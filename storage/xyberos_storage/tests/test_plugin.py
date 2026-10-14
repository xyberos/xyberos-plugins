"""Tests for loading the storage plugin into a Xyberos app."""

from __future__ import annotations

from xyberos import create_app

from xyberos_storage import StoragePlugin


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def get_paginator(self, _name):
        return self

    def paginate(self, **kwargs):
        prefix = kwargs.get("Prefix", "")
        return [{"Contents": [{"Key": k} for k in self.objects if k.startswith(prefix)]}]

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {"Body": __import__("io").BytesIO(self.objects[kwargs["Key"]])}


def test_plugin_registers_and_executes(tmp_path):
    from xyberos_storage import S3Store

    client = _FakeS3Client()
    app = create_app()
    # Build the plugin but swap in a store with the fake client.
    plugin = StoragePlugin(provider="s3", bucket="bucket")
    store = S3Store("bucket", client=client)
    plugin._provider = "s3"
    # Replace the plugin's object_store with the fake-backed one for the test.
    plugin.object_store = lambda: store  # type: ignore[method-assign]
    app.load_plugin(plugin)

    assert "storage_list" in app.tools.names

    src = tmp_path / "src.txt"
    src.write_bytes(b"hello")
    app.tools.execute("storage_upload", None, key="dir/a.txt", file_path=str(src))
    assert app.tools.execute("storage_list", None, prefix="dir/") == ["dir/a.txt"]

    out = tmp_path / "out.txt"
    assert app.tools.execute("storage_download", None, key="dir/a.txt", output_path=str(out)) == str(out)
    assert out.read_bytes() == b"hello"

    app.unload_plugin("storage")

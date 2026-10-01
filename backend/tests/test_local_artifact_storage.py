import hashlib
from io import BytesIO

import pytest

from modules.documents.storage import LocalArtifactStorage, sha256_file


def test_local_storage_streams_upload_and_keeps_legacy_uri(tmp_path):
    payload = b"document-data" * 100_000
    storage = LocalArtifactStorage(tmp_path / "uploads")
    saved = storage.save_stream("document.pdf", BytesIO(payload))
    assert saved["size_bytes"] == len(payload)
    assert saved["sha256"] == hashlib.sha256(payload).hexdigest()
    assert saved["uri"] == str((tmp_path / "uploads" / "document.pdf").resolve())
    assert sha256_file(saved["uri"]) == saved["sha256"]


def test_local_storage_rejects_path_traversal(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.save_stream("../outside.pdf", BytesIO(b"bad"))
    assert list(tmp_path.iterdir()) == []

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

from core.config import settings
from modules.documents import storage as storage_module
from modules.documents.storage import (
    LOCAL, S3, LocalArtifactStorage, S3ArtifactStorage, artifact_storage, storage_for_provider,
)

BUCKET = "nckh-test-artifacts"


@pytest.fixture
def s3(monkeypatch):
    for name, value in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                        ("AWS_DEFAULT_REGION", "us-east-1")):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(settings, "s3_bucket", BUCKET)
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_prefix", "nckh")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_s3_stream_upload_records_checksum_and_streams_back(s3):
    storage = S3ArtifactStorage(bucket=BUCKET, prefix="nckh/uploads", client=s3)
    payload = b"pdf-bytes" * 300_000  # larger than one chunk
    saved = storage.save_stream("doc.pdf", BytesIO(payload), content_type="application/pdf")
    assert saved == {"provider": S3, "uri": "nckh/uploads/doc.pdf",
                     "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}
    head = s3.head_object(Bucket=BUCKET, Key=saved["uri"])
    assert head["ContentType"] == "application/pdf"
    assert storage.stored_sha256(saved["uri"]) == saved["sha256"]
    assert b"".join(storage.iter_bytes(saved["uri"])) == payload
    assert storage.exists(saved["uri"]) and not storage.exists("nckh/uploads/other.pdf")
    with pytest.raises(ValueError):
        storage.save_stream("../escape.pdf", BytesIO(b"x"))


def test_s3_content_addressed_blobs_are_deduplicated(s3, tmp_path):
    storage = S3ArtifactStorage(bucket=BUCKET, prefix="nckh/artifact_blobs", client=s3)
    first_file = tmp_path / "a.raw.json.gz"
    first_file.write_bytes(b"same-content")
    first = storage.save_content_addressed(first_file, content_type="application/gzip")
    digest = hashlib.sha256(b"same-content").hexdigest()
    # Same naming as local blobs: the last two suffixes are kept.
    assert first["uri"] == f"nckh/artifact_blobs/{digest[:2]}/{digest}.json.gz"
    assert first["reused"] is False and not first_file.exists()
    second_file = tmp_path / "b.raw.json.gz"
    second_file.write_bytes(b"same-content")
    second = storage.save_content_addressed(second_file)
    assert second["reused"] is True and second["uri"] == first["uri"]
    assert not second_file.exists()


def test_s3_local_copy_is_removed_after_use_and_delete_works(s3):
    storage = S3ArtifactStorage(bucket=BUCKET, prefix="nckh/uploads", client=s3)
    saved = storage.save_stream("scan.pdf", BytesIO(b"scan"))
    with storage.local_copy(saved["uri"]) as path:
        assert path.read_bytes() == b"scan"
        copied = path
    assert not copied.exists() and not copied.parent.exists()
    storage.delete(saved["uri"])
    assert not storage.exists(saved["uri"])


def test_provider_selection_for_new_and_existing_files(s3, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "storage_provider", "local")
    local = artifact_storage("uploads")
    assert isinstance(local, LocalArtifactStorage) and local.provider == LOCAL
    assert isinstance(artifact_storage("uploads", provider="s3"), S3ArtifactStorage)
    monkeypatch.setattr(settings, "storage_provider", "s3")
    avatars = artifact_storage("avatars")
    assert isinstance(avatars, S3ArtifactStorage)
    assert avatars.uri_for("me.png") == "nckh/avatars/me.png"
    saved = avatars.save_stream("me.png", BytesIO(b"png"))
    # Reads use the provider recorded with the file and the full stored key.
    reader = storage_for_provider("S3")
    assert b"".join(reader.iter_bytes(saved["uri"])) == b"png"
    assert isinstance(storage_for_provider(None), LocalArtifactStorage)
    with pytest.raises(ValueError):
        artifact_storage("unknown")


def test_source_pdf_route_streams_object_storage(s3, monkeypatch):
    from modules.questions import router as question_router

    storage = S3ArtifactStorage(bucket=BUCKET, prefix="nckh/uploads", client=s3)
    saved = storage.save_stream("nguồn.pdf", BytesIO(b"%PDF-1.7"))
    service = SimpleNamespace(source_pdf_artifact=lambda *_a: {
        "provider": "S3", "uri": saved["uri"], "filename": "Đề nguồn.pdf",
        "mime_type": "application/pdf",
    })
    response = question_router.get_question_source_pdf("q", SimpleNamespace(), service)
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment; filename*=utf-8''")

    async def body() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    assert asyncio.run(body()) == b"%PDF-1.7"
    missing = SimpleNamespace(source_pdf_artifact=lambda *_a: {
        "provider": "S3", "uri": "nckh/uploads/gone.pdf", "filename": "x.pdf",
        "mime_type": "application/pdf",
    })
    with pytest.raises(question_router.HTTPException) as exc:
        question_router.get_question_source_pdf("q", SimpleNamespace(), missing)
    assert exc.value.status_code == 404


def test_avatar_route_reads_s3_then_local_then_default(s3, monkeypatch, tmp_path):
    from modules.users import router as users_router

    monkeypatch.setattr(settings, "storage_provider", "s3")
    monkeypatch.setattr(users_router, "AVATAR_UPLOAD_DIR", tmp_path)
    artifact_storage("avatars").save_stream("cloud.png", BytesIO(b"cloud"))
    (tmp_path / "legacy.png").write_bytes(b"legacy")

    async def body(response) -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    cloud = users_router.get_avatar("cloud.png")
    assert cloud.media_type == "image/png" and asyncio.run(body(cloud)) == b"cloud"
    legacy = users_router.get_avatar("legacy.png")
    assert Path(legacy.path) == tmp_path / "legacy.png"
    assert users_router.get_avatar("missing.png").media_type == "image/svg+xml"
    with pytest.raises(users_router.HTTPException):
        users_router.get_avatar("..")


def test_storage_module_never_reads_credentials_from_settings():
    source = Path(storage_module.__file__).read_text(encoding="utf-8")
    assert "aws_access_key_id" not in source and "aws_secret_access_key" not in source

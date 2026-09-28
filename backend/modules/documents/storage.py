"""Artifact storage boundary for uploads, OCR artifacts and avatars.

Every stored file is described by ``provider`` + ``uri``:

* ``LOCAL`` - ``uri`` is the absolute filesystem path (legacy format).
* ``S3``    - ``uri`` is the object key; the bucket comes from the environment,
  so moving buckets never rewrites database rows.

New files go to ``STORAGE_PROVIDER``; existing files are always read from the
provider recorded with them, so a partially migrated system keeps working.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator
from uuid import uuid4

LOCAL = "LOCAL"
S3 = "S3"
CHUNK_SIZE = 1024 * 1024

# Logical areas -> local directory setting.
CATEGORY_DIRS = {
    "uploads": "upload_dir",
    "artifact_blobs": "artifact_blob_dir",
    "avatars": None,  # <upload_dir>/avatars
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_name(name: str) -> None:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Tên file lưu trữ không hợp lệ")


def _blob_name(path: Path, digest: str) -> str:
    suffix = "".join(path.suffixes[-2:]) or ".blob"
    return f"{digest[:2]}/{digest}{suffix}"


class LocalArtifactStorage:
    provider = LOCAL

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def uri_for(self, name: str) -> str:
        _check_name(name)
        return str(self.root / name)

    def save_stream(self, name: str, source: BinaryIO, *,
                    content_type: str | None = None) -> dict:
        """Write one stream atomically and return its URI plus checksum."""
        _check_name(name)
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / name
        temporary = self.root / f".{name}.{uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                for block in iter(lambda: source.read(CHUNK_SIZE), b""):
                    output.write(block)
                    digest.update(block)
                    size += len(block)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return {"provider": LOCAL, "uri": str(destination),
                "sha256": digest.hexdigest(), "size_bytes": size}

    def save_content_addressed(self, source: str | Path, *,
                               content_type: str | None = None) -> dict:
        """Move a new file into sha256-addressed storage, reusing an identical blob."""
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        digest = sha256_file(source_path)
        destination = self.root / _blob_name(source_path, digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        reused = destination.exists()
        if destination.resolve() != source_path:
            if reused:
                source_path.unlink()
            else:
                os.replace(source_path, destination)
        return {"provider": LOCAL, "uri": str(destination), "sha256": digest,
                "size_bytes": destination.stat().st_size, "reused": reused}

    def exists(self, uri: str) -> bool:
        return Path(uri).is_file()

    def iter_bytes(self, uri: str) -> Iterator[bytes]:
        with Path(uri).open("rb") as source:
            yield from iter(lambda: source.read(CHUNK_SIZE), b"")

    @contextmanager
    def local_copy(self, uri: str) -> Iterator[Path]:
        # Local files are already on disk; OCR can read them in place.
        yield Path(uri)

    def delete(self, uri: str) -> None:
        Path(uri).unlink(missing_ok=True)


class S3ArtifactStorage:
    """S3-compatible storage (AWS S3, MinIO, R2, GCS interoperability)."""

    provider = S3

    def __init__(self, *, bucket: str, prefix: str = "", client=None):
        if not bucket:
            raise RuntimeError("STORAGE_PROVIDER=s3 requires S3_BUCKET")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client or _s3_client()

    def uri_for(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def _put(self, key: str, body: BinaryIO, *, sha256: str,
             content_type: str | None) -> None:
        extra = {"Metadata": {"sha256": sha256}}
        if content_type:
            extra["ContentType"] = content_type
        self.client.upload_fileobj(body, self.bucket, key, ExtraArgs=extra)

    def save_stream(self, name: str, source: BinaryIO, *,
                    content_type: str | None = None) -> dict:
        _check_name(name)
        # Spool first so the checksum is known before the object is written;
        # small files stay in memory, large ones spill to a temporary file.
        digest = hashlib.sha256()
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=16 * CHUNK_SIZE) as spool:
            for block in iter(lambda: source.read(CHUNK_SIZE), b""):
                spool.write(block)
                digest.update(block)
                size += len(block)
            spool.seek(0)
            key = self.uri_for(name)
            self._put(key, spool, sha256=digest.hexdigest(), content_type=content_type)
        return {"provider": S3, "uri": key, "sha256": digest.hexdigest(), "size_bytes": size}

    def save_content_addressed(self, source: str | Path, *,
                               content_type: str | None = None) -> dict:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        digest = sha256_file(source_path)
        key = self.uri_for(_blob_name(source_path, digest))
        size = source_path.stat().st_size
        reused = self.exists(key)
        if not reused:
            with source_path.open("rb") as body:
                self._put(key, body, sha256=digest, content_type=content_type)
        source_path.unlink()
        return {"provider": S3, "uri": key, "sha256": digest,
                "size_bytes": size, "reused": reused}

    def put_file(self, key: str, path: str | Path, *, sha256: str,
                 content_type: str | None = None) -> None:
        """Upload one local file under a full object key (used by migration)."""
        if not key or ".." in Path(key).parts or key.startswith("/"):
            raise ValueError("Object key không hợp lệ")
        with Path(path).open("rb") as body:
            self._put(key, body, sha256=sha256, content_type=content_type)

    def exists(self, uri: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=uri)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def stored_sha256(self, uri: str) -> str | None:
        head = self.client.head_object(Bucket=self.bucket, Key=uri)
        return (head.get("Metadata") or {}).get("sha256")

    def iter_bytes(self, uri: str) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=uri)["Body"]
        try:
            yield from body.iter_chunks(CHUNK_SIZE)
        finally:
            body.close()

    @contextmanager
    def local_copy(self, uri: str) -> Iterator[Path]:
        """Download to a temporary file for libraries that need a real path."""
        directory = Path(tempfile.mkdtemp(prefix="artifact-"))
        target = directory / Path(uri).name
        try:
            self.client.download_file(self.bucket, uri, str(target))
            yield target
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def delete(self, uri: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=uri)


def _s3_client():
    import boto3

    from core.config import settings

    # Credentials come from the standard AWS chain (env, profile, workload
    # identity); they are never stored in settings or the database.
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region or None,
    )


def _local_root(category: str) -> Path:
    from core.config import resolve_path, settings

    if category == "avatars":
        return resolve_path(settings.upload_dir) / "avatars"
    return resolve_path(getattr(settings, CATEGORY_DIRS[category]))


def artifact_storage(category: str, provider: str | None = None):
    """Storage for new files of one area ("uploads", "artifact_blobs", "avatars").

    ``provider`` overrides STORAGE_PROVIDER (the migration writes to S3 while
    the application may still be configured for local storage).
    """
    from core.config import settings

    if category not in CATEGORY_DIRS:
        raise ValueError(f"Unknown storage category: {category}")
    if (provider or settings.storage_provider).lower() == "s3":
        prefix = "/".join(part for part in (settings.s3_prefix, category) if part)
        return S3ArtifactStorage(bucket=settings.s3_bucket, prefix=prefix)
    return LocalArtifactStorage(_local_root(category))


def storage_for_provider(provider: str | None):
    """Storage able to read files recorded with ``provider`` (full URIs)."""
    from core.config import settings

    if (provider or LOCAL).upper() == S3:
        return S3ArtifactStorage(bucket=settings.s3_bucket)
    return LocalArtifactStorage(_local_root("uploads"))

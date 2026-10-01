"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import hashlib
import json
import os
from datetime import datetime, timezone

import boto3
import pytest
from bson import ObjectId
from moto import mock_aws

from core.config import settings
from core.postgres import postgres_connection
from db import migrate_artifact_storage as migration
from db.copy_business_data import projected_rows, upsert
from modules.documents.postgres_repository import PostgresDocumentRepository
from modules.documents.storage import S3ArtifactStorage, storage_for_provider


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)
BUCKET = "nckh-migration-test"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_local_artifacts_move_to_s3_with_manifest_and_checksum_guards(monkeypatch, tmp_path):
    for name, value in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                        ("AWS_DEFAULT_REGION", "us-east-1")):
        monkeypatch.setenv(name, value)
    uploads, blobs = tmp_path / "uploads", tmp_path / "blobs"
    for key, value in (("document_store", "postgres"), ("user_store", "postgres"),
                       ("catalog_store", "postgres"), ("upload_dir", str(uploads)),
                       ("artifact_blob_dir", str(blobs)), ("s3_bucket", BUCKET),
                       ("s3_prefix", "nckh"), ("s3_region", "us-east-1"),
                       ("s3_endpoint_url", "")):
        monkeypatch.setattr(settings, key, value)
    original, blob, drifted, conflicting = b"%PDF-original", b"raw-json", b"edited", b"clash"
    (uploads / "avatars").mkdir(parents=True)
    (uploads / "avatars" / "u1.png").write_bytes(b"avatar")
    original_path = uploads / "doc_source.pdf"
    original_path.write_bytes(original)
    blob_path = blobs / _sha(blob)[:2] / f"{_sha(blob)}.json.gz"
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(blob)
    drifted_path = uploads / "drifted.pdf"
    drifted_path.write_bytes(drifted)
    conflict_path = uploads / "conflict.pdf"
    conflict_path.write_bytes(conflicting)
    now = datetime.now(timezone.utc)
    document_id = ObjectId()
    ids = {name: ObjectId() for name in ("original", "blob", "drifted", "missing", "conflict")}

    def artifact(name, path, sha, kind="ORIGINAL_PDF"):
        return {"_id": ids[name], "type": kind, "document_version": 1,
                "storage": {"provider": "LOCAL", "uri": str(path), "gridfs_file_id": None},
                "mime_type": "application/pdf", "size_bytes": 1, "sha256": sha,
                "is_current": True, "created_at": now}

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        target = S3ArtifactStorage(bucket=BUCKET, client=client)
        target.put_file("nckh/uploads/conflict.pdf", original_path, sha256=_sha(original))
        try:
            with postgres_connection() as conn:
                for table, row in projected_rows("documents", {
                    "_id": document_id, "title": "Storage", "original_filename": "doc.pdf",
                    "status": "READY", "current_version": 1, "created_at": now, "updated_at": now,
                    "artifacts": [
                        artifact("original", original_path, _sha(original)),
                        artifact("blob", blob_path, _sha(blob), "RAW_EXTRACTION_JSON"),
                        artifact("drifted", drifted_path, _sha(b"what the DB expected")),
                        artifact("missing", uploads / "gone.pdf", _sha(b"gone")),
                        artifact("conflict", conflict_path, _sha(conflicting)),
                    ],
                }):
                    upsert(conn, table, row)
            manifest = tmp_path / "manifest.jsonl"

            planned = migration.run(apply=False, manifest_path=manifest, target=target)
            assert planned["artifacts"] == {"planned": 3, "checksum_mismatch": 1, "missing": 1}
            assert planned["avatars"] == {"planned": 1}
            assert not target.exists("nckh/uploads/doc_source.pdf")

            applied = migration.run(apply=True, manifest_path=manifest, target=target,
                                    verify_content=True)
            assert applied["artifacts"] == {"uploaded": 2, "checksum_mismatch": 1,
                                            "missing": 1, "key_conflict": 1}
            assert applied["avatars"] == {"uploaded": 1}
            with postgres_connection() as conn:
                rows = {row["id"]: row for row in conn.execute(
                    "SELECT id, storage_provider, storage_key, payload FROM document_artifacts "
                    "WHERE document_id=%s", (str(document_id),)).fetchall()}
            moved = rows[str(ids["original"])]
            assert moved["storage_provider"] == "S3"
            assert moved["storage_key"] == "nckh/uploads/doc_source.pdf"
            assert moved["payload"]["storage"] == {"provider": "S3", "gridfs_file_id": None,
                                                   "uri": "nckh/uploads/doc_source.pdf"}
            assert rows[str(ids["blob"])]["storage_key"] == (
                f"nckh/artifact_blobs/{_sha(blob)[:2]}/{_sha(blob)}.json.gz")
            for name in ("drifted", "missing", "conflict"):
                assert rows[str(ids[name])]["storage_provider"] == "LOCAL"
            assert original_path.exists(), "local files are never deleted"

            # The application now reads the migrated file from S3.
            document = PostgresDocumentRepository().find_by_id(document_id)
            stored = next(item for item in document["artifacts"] if item["_id"] == ids["original"])
            assert stored["storage"]["provider"] == "S3"
            reader = storage_for_provider("S3")
            assert b"".join(reader.iter_bytes(stored["storage"]["uri"])) == original

            again = migration.run(apply=True, manifest_path=manifest, target=target)
            assert again["artifacts"] == {"checksum_mismatch": 1, "missing": 1, "key_conflict": 1}
            assert again["avatars"] == {"reused": 1}
            lines = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            assert [line["apply"] for line in lines if line["kind"] == "batch"] == [False, True, True]
            assert len({line["migration_batch_id"] for line in lines if line["kind"] == "batch"}) == 3
            assert all("status" in line for line in lines if line["kind"] != "batch")
        finally:
            with postgres_connection() as conn:
                conn.execute("DELETE FROM document_artifacts WHERE document_id=%s", (str(document_id),))
                conn.execute("DELETE FROM document_subjects WHERE document_id=%s", (str(document_id),))
                conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))

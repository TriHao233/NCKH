"""Copy local document artifacts and avatars to S3-compatible object storage.

Dry-run by default: it only reports what would move. With --apply, each file
is uploaded under a stable key, its SHA-256 is verified against the database
and the stored object, and only then is the artifact row switched to S3 (one
row per transaction, guarded by its previous location). Local files are never
deleted; remove them separately after the rollback window.

Every run writes a JSONL manifest (one header line, then one line per file)
so the batch can be audited or resumed. Re-running is safe: objects that
already hold the same checksum are reused.

    python -m db.migrate_artifact_storage --manifest data/storage-manifest.jsonl
    python -m db.migrate_artifact_storage --apply --manifest ... [--verify-content]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from psycopg.types.json import Jsonb

from core.config import resolve_path, settings
from core.postgres import postgres_connection
from modules.documents.storage import S3ArtifactStorage, sha256_file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def object_key(local_path: Path, *, prefix: str, blob_root: Path) -> str:
    """Stable key: blobs keep their content-addressed layout, originals their name."""
    resolved = local_path.resolve()
    if resolved.is_relative_to(blob_root):
        relative = resolved.relative_to(blob_root).as_posix()
        category = "artifact_blobs"
    else:
        relative, category = resolved.name, "uploads"
    return "/".join(part for part in (prefix, category, relative) if part)


def _verify(target: S3ArtifactStorage, key: str, sha256: str, *, content: bool) -> bool:
    if target.stored_sha256(key) != sha256:
        return False
    if not content:
        return True
    digest = hashlib.sha256()
    for block in target.iter_bytes(key):
        digest.update(block)
    return digest.hexdigest() == sha256


def _upload(target: S3ArtifactStorage, key: str, path: Path, sha256: str,
            content_type: str | None) -> str:
    """Upload unless the same content is already there; return the action taken."""
    if target.exists(key):
        return "reused" if target.stored_sha256(key) == sha256 else "key_conflict"
    target.put_file(key, path, sha256=sha256, content_type=content_type)
    return "uploaded"


def migrate_artifacts(conn, target: S3ArtifactStorage, manifest: TextIO, *,
                      apply: bool, prefix: str, blob_root: Path,
                      verify_content: bool = False, limit: int | None = None) -> dict:
    rows = conn.execute(
        """SELECT id, document_id, artifact_type, storage_key, checksum_sha256, mime_type
           FROM document_artifacts WHERE storage_provider='LOCAL'
           ORDER BY created_at, id""" + (" LIMIT %s" if limit else ""),
        (limit,) if limit else (),
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        path = Path(row["storage_key"])
        if not path.is_absolute():
            path = resolve_path(path)
        entry = {"kind": "artifact", "artifact_id": row["id"], "document_id": row["document_id"],
                 "artifact_type": row["artifact_type"], "source": str(path)}
        if not path.is_file():
            status = "missing"
        else:
            sha256 = sha256_file(path)
            key = object_key(path, prefix=prefix, blob_root=blob_root)
            entry.update(sha256=sha256, size_bytes=path.stat().st_size, key=key)
            if row["checksum_sha256"] and row["checksum_sha256"] != sha256:
                status = "checksum_mismatch"
            elif not apply:
                status = "planned"
            else:
                status = _upload(target, key, path, sha256, row["mime_type"])
                if status in {"uploaded", "reused"}:
                    if not _verify(target, key, sha256, content=verify_content):
                        status = "verify_failed"
                    else:
                        switched = conn.execute(
                            """UPDATE document_artifacts SET storage_provider='S3',
                                 storage_key=%s,
                                 payload=jsonb_set(payload, '{storage}',
                                   COALESCE(payload->'storage','{}'::jsonb) || %s)
                               WHERE id=%s AND storage_provider='LOCAL' AND storage_key=%s""",
                            (key, Jsonb({"provider": "S3", "uri": key}),
                             row["id"], row["storage_key"]),
                        ).rowcount
                        conn.commit()
                        if not switched:
                            status = "changed_concurrently"
        entry.update(status=status, at=_now())
        manifest.write(json.dumps(entry, ensure_ascii=False) + "\n")
        counts[status] = counts.get(status, 0) + 1
    return counts


def migrate_avatars(target: S3ArtifactStorage, manifest: TextIO, *, apply: bool,
                    prefix: str, avatar_root: Path, verify_content: bool = False) -> dict:
    counts: dict[str, int] = {}
    for path in sorted(avatar_root.glob("*")) if avatar_root.is_dir() else []:
        if not path.is_file():
            continue
        sha256 = sha256_file(path)
        key = "/".join(part for part in (prefix, "avatars", path.name) if part)
        entry = {"kind": "avatar", "source": str(path), "key": key, "sha256": sha256,
                 "size_bytes": path.stat().st_size}
        if not apply:
            status = "planned"
        else:
            status = _upload(target, key, path, sha256, None)
            if status in {"uploaded", "reused"} and not _verify(
                    target, key, sha256, content=verify_content):
                status = "verify_failed"
        entry.update(status=status, at=_now())
        manifest.write(json.dumps(entry, ensure_ascii=False) + "\n")
        counts[status] = counts.get(status, 0) + 1
    return counts


def run(*, apply: bool, manifest_path: Path, verify_content: bool = False,
        limit: int | None = None, target: S3ArtifactStorage | None = None) -> dict:
    target = target or S3ArtifactStorage(bucket=settings.s3_bucket)
    prefix = settings.s3_prefix
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    batch_id = uuid4().hex
    with manifest_path.open("a", encoding="utf-8") as manifest:
        manifest.write(json.dumps({
            "kind": "batch", "migration_batch_id": batch_id, "started_at": _now(),
            "bucket": target.bucket, "prefix": prefix, "apply": apply,
        }) + "\n")
        with postgres_connection() as conn:
            artifacts = migrate_artifacts(
                conn, target, manifest, apply=apply, prefix=prefix,
                blob_root=resolve_path(settings.artifact_blob_dir),
                verify_content=verify_content, limit=limit,
            )
        avatars = migrate_avatars(
            target, manifest, apply=apply, prefix=prefix,
            avatar_root=resolve_path(settings.upload_dir) / "avatars",
            verify_content=verify_content,
        )
    return {"migration_batch_id": batch_id, "artifacts": artifacts, "avatars": avatars}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Upload and switch rows to S3 (default: dry-run).")
    parser.add_argument("--manifest", required=True, type=Path,
                        help="JSONL manifest to append this batch to.")
    parser.add_argument("--verify-content", action="store_true",
                        help="Re-download each object and hash it, not only its metadata.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process this many artifacts (for rehearsals).")
    args = parser.parse_args()
    if settings.document_store != "postgres":
        raise SystemExit("DOCUMENT_STORE=postgres is required: artifacts are read from PostgreSQL")
    result = run(apply=args.apply, manifest_path=args.manifest,
                 verify_content=args.verify_content, limit=args.limit)
    print(json.dumps(result, indent=2))
    problems = {"missing", "checksum_mismatch", "key_conflict", "verify_failed",
                "changed_concurrently"}
    if any(result[group].get(status) for group in ("artifacts", "avatars") for status in problems):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

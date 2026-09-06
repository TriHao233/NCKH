"""Compare restored Mongo databases and artifact storage with their sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo import MongoClient


def _hash_documents(collection) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for document in collection.find().sort("_id", 1):
        digest.update(
            json_util.dumps(
                document,
                json_options=json_util.CANONICAL_JSON_OPTIONS,
                sort_keys=True,
            ).encode("utf-8")
        )
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def _database_manifest(client: MongoClient, name: str) -> dict:
    database = client[name]
    return {
        collection_name: dict(
            zip(
                ("count", "sha256"),
                _hash_documents(database[collection_name]),
            )
        )
        for collection_name in sorted(database.list_collection_names())
        if not collection_name.startswith("system.")
    }


def _file_manifest(root: Path) -> dict:
    return {
        str(path.relative_to(root)).replace("\\", "/"): {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True)
    parser.add_argument("--database-pair", action="append", required=True)
    parser.add_argument("--artifacts-source", type=Path, required=True)
    parser.add_argument("--artifacts-restored", type=Path, required=True)
    parser.add_argument("--dump-file", type=Path, action="append", default=[])
    parser.add_argument("--rto-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    client = MongoClient(args.uri, retryWrites=False, tz_aware=True)
    database_results = []
    for pair in args.database_pair:
        source_name, restored_name = pair.split(":", 1)
        source = _database_manifest(client, source_name)
        restored = _database_manifest(client, restored_name)
        database_results.append(
            {
                "source": source_name,
                "restored": restored_name,
                "source_manifest": source,
                "restored_manifest": restored,
                "passed": source == restored,
            }
        )
    source_artifacts = _file_manifest(args.artifacts_source.resolve())
    restored_artifacts = _file_manifest(args.artifacts_restored.resolve())
    dump_files = [
        {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in args.dump_file
    ]
    checks = {
        "all_databases_match": all(item["passed"] for item in database_results),
        "artifact_storage_matches": source_artifacts == restored_artifacts,
        "dump_files_non_empty": bool(dump_files)
        and all(item["bytes"] > 0 for item in dump_files),
    }
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "rpo_seconds": 0,
        "rto_seconds": round(args.rto_seconds, 3),
        "databases": database_results,
        "artifact_storage": {
            "source_file_count": len(source_artifacts),
            "restored_file_count": len(restored_artifacts),
            "source_manifest": source_artifacts,
            "restored_manifest": restored_artifacts,
        },
        "dump_files": dump_files,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], **checks}, ensure_ascii=False))
    client.close()
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

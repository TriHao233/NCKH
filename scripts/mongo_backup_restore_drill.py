"""Create a checksummed mongodump and restore it only into an explicit drill database."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def file_manifest(root: Path) -> list[dict]:
    return [
        {
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, shell=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True)
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--drill-db", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.drill_db.endswith("_restore_drill") or args.drill_db == args.source_db:
        parser.error("drill-db phải khác source và kết thúc bằng _restore_drill")
    started = datetime.now(timezone.utc)
    dump_dir = args.output.resolve()
    dump_dir.mkdir(parents=True, exist_ok=True)
    run(
        ["mongodump", "--uri", args.uri, "--db", args.source_db, "--out", str(dump_dir)]
    )
    run(
        [
            "mongorestore",
            "--uri",
            args.uri,
            "--nsFrom",
            f"{args.source_db}.*",
            "--nsTo",
            f"{args.drill_db}.*",
            str(dump_dir / args.source_db),
        ]
    )
    manifest = {
        "source_db": args.source_db,
        "drill_db": args.drill_db,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "files": file_manifest(dump_dir / args.source_db),
    }
    (dump_dir / "restore-drill-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

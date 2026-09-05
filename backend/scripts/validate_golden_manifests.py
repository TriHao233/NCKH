from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from modules.documents.ingest.manifest import RawGoldenManifest, validate_manifest_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw/verified golden-corpus manifests without running ingest")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--manifest-dir", type=Path)
    parser.add_argument("--print-schema", action="store_true")
    args = parser.parse_args()
    if args.print_schema:
        print(json.dumps(RawGoldenManifest.model_json_schema(), ensure_ascii=False, indent=2))
        return 0
    if args.corpus is None:
        parser.error("--corpus is required unless --print-schema is used")
    corpus = args.corpus.resolve()
    manifest_dir = (args.manifest_dir or corpus / "manifests" / "raw-generated").resolve()
    manifest_paths = sorted(manifest_dir.glob("*.json")) if manifest_dir.is_dir() else []
    reports = [
        validate_manifest_file(path, corpus_root=corpus, workspace_root=WORKSPACE_DIR).to_dict()
        for path in manifest_paths
    ]
    summary = {
        "corpus": str(corpus),
        "manifest_directory": str(manifest_dir),
        "count": len(reports),
        "valid_count": sum(bool(report["valid"]) for report in reports),
        "status_counts": {
            status: sum(report["status"] == status for report in reports)
            for status in (
                "verified",
                "raw_generated",
                "manifest_conflict",
                "manifest_failed",
                "unsupported",
            )
        },
        "reports": reports,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if reports and all(report["valid"] for report in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())

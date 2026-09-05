from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest_path = ROOT / "docs" / "baseline_dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            if item.get("required_in_repository", True):
                errors.append(f"missing: {item['path']}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            errors.append(f"checksum mismatch: {item['path']}")
        if path.stat().st_size != item["size_bytes"]:
            errors.append(f"size mismatch: {item['path']}")
    required_files = [
        ROOT / ".python-version",
        ROOT / ".nvmrc",
        ROOT / "backend" / ".env.example",
        ROOT / "frontend" / ".env.example",
        ROOT / "docs" / "MOODLE_INTEGRATION_CONTRACT.md",
        ROOT / "docs" / "runtime_manifest.json",
    ]
    errors.extend(f"missing: {path.relative_to(ROOT)}" for path in required_files if not path.is_file())
    if errors:
        print("baseline verification failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"baseline {manifest['manifest_version']} verified ({len(manifest['files'])} file fixtures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Local artifact storage boundary used by document upload and OCR."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4


class LocalArtifactStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def save_stream(self, name: str, source: BinaryIO) -> dict:
        """Write one stream and return a legacy-compatible URI plus checksum."""
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Tên file lưu trữ không hợp lệ")
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / name
        temporary = self.root / f".{name}.{uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(block)
                    digest.update(block)
                    size += len(block)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return {"uri": str(destination), "sha256": digest.hexdigest(), "size_bytes": size}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

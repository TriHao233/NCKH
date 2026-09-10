from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from modules.documents.ingest.models import BlockType


ManifestStatus = Literal[
    "verified",
    "raw_generated",
    "manifest_conflict",
    "manifest_failed",
    "unsupported",
]

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

GENERATOR_RELEASE_TIMESTAMPS = {
    "qbank-raw-manifest/2026-09-04.1": "2026-09-04T00:00:00Z",
}

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ManifestReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    sha256: str
    status: str | None = None
    evidence: str | None = None
    truth_page_numbers: list[int] | None = None
    local_page_mapping: dict[str, int] | None = None
    case_ids: list[str] | None = None

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
        return normalized


class RawGoldenManifest(BaseModel):
    """Strict, executable contract for verified and generated golden-corpus manifests."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: str
    manifest_status: ManifestStatus
    requires_human_review: bool
    fixture_id: str
    source_file: str
    source_file_name: str
    relative_path: str
    file_extension: str
    mime_type: str
    file_size: int = Field(ge=0)
    sha256: str
    language_detected: str
    document_category: str
    page_count: int | None = Field(default=None, ge=1)
    source_unit_count: int | None = Field(default=None, ge=1)
    has_text_layer: bool | None
    is_scanned: bool
    is_mixed: bool
    expected_content_types: list[BlockType]
    detected_code_locations: list[dict[str, Any]]
    detected_table_locations: list[dict[str, Any]]
    detected_formula_locations: list[dict[str, Any]]
    detected_image_or_diagram_locations: list[dict[str, Any]]
    ground_truth_available: bool
    ground_truth_independent: bool = False
    ground_truth_references: list[ManifestReference]
    rag_questions_available: bool
    rag_question_references: list[ManifestReference]
    parser_selected: str
    extractor_strategy: str
    detection_confidence: float = Field(ge=0.0, le=1.0)
    generator_version: str
    generation_timestamp: str
    eligible_for_cer_wer: bool = False
    detection_evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str]

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
        return normalized

    @field_validator("file_extension")
    @classmethod
    def normalize_extension(cls, value: str) -> str:
        normalized = value.lower()
        if not normalized.startswith("."):
            raise ValueError("file_extension must start with a dot")
        return normalized

    @field_validator("generation_timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("generation_timestamp must include a UTC offset")
        return value

    @model_validator(mode="after")
    def validate_consistency(self) -> "RawGoldenManifest":
        if self.page_count is None and self.source_unit_count is None:
            raise ValueError("page_count or source_unit_count is required")
        if self.manifest_status == "raw_generated" and not self.requires_human_review:
            raise ValueError("raw_generated manifests must require human review")
        if self.ground_truth_available and not self.ground_truth_references:
            raise ValueError("ground_truth_available requires at least one reference")
        if self.ground_truth_independent and not self.ground_truth_available:
            raise ValueError("independent ground truth must also be available")
        if self.rag_questions_available and not self.rag_question_references:
            raise ValueError("rag_questions_available requires at least one reference")
        if self.eligible_for_cer_wer and not (
            self.ground_truth_available and self.ground_truth_independent and self.ground_truth_references
        ):
            raise ValueError("CER/WER requires available, independently sourced ground truth")
        return self


@dataclass
class ManifestValidationReport:
    manifest_path: str
    status: ManifestStatus
    fixture_id: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    canonical_sha256: str | None = None
    byte_deterministic: bool = False

    @property
    def valid(self) -> bool:
        return self.status in {"verified", "raw_generated"} and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "fixture_id": self.fixture_id,
            "status": self.status,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "canonical_sha256": self.canonical_sha256,
            "byte_deterministic": self.byte_deterministic,
        }


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manifest_bytes(manifest: RawGoldenManifest) -> bytes:
    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    )
    return (payload + "\n").encode("utf-8")


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _sniff_mime(path: Path) -> str | None:
    prefix = path.read_bytes()[:8]
    suffix = path.suffix.lower()
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or prefix.lstrip().startswith(b"{\\rtf"):
        return "application/msword"
    if suffix == ".docx" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as package:
            names = set(package.namelist())
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return MIME_BY_EXTENSION[".docx"]
    if suffix in {".md", ".markdown", ".txt"}:
        try:
            path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return None
        return MIME_BY_EXTENSION[suffix]
    return None


def _resolve_reference(corpus_root: Path, relative_path: str) -> Path | None:
    candidate = (corpus_root / relative_path).resolve()
    return candidate if _within(corpus_root, candidate) else None


def validate_manifest_file(
    manifest_path: str | Path,
    *,
    corpus_root: str | Path,
    workspace_root: str | Path,
) -> ManifestValidationReport:
    manifest_file = Path(manifest_path).resolve()
    corpus = Path(corpus_root).resolve()
    workspace = Path(workspace_root).resolve()
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = RawGoldenManifest.model_validate(payload)
    except Exception as exc:
        return ManifestValidationReport(
            manifest_path=str(manifest_file),
            status="manifest_failed",
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    report = ManifestValidationReport(
        manifest_path=str(manifest_file),
        fixture_id=manifest.fixture_id,
        status=manifest.manifest_status,
    )
    if manifest.manifest_status in {"manifest_conflict", "manifest_failed", "unsupported"}:
        report.errors.append(f"manifest declares terminal status {manifest.manifest_status}")
        return report

    source = _resolve_reference(corpus, manifest.relative_path)
    if source is None:
        report.status = "manifest_failed"
        report.errors.append("relative_path escapes corpus root")
        return report
    if not source.is_file():
        report.status = "manifest_failed"
        report.errors.append(f"source file does not exist: {manifest.relative_path}")
        return report

    declared_source = Path(manifest.source_file)
    if not declared_source.is_absolute():
        declared_source = workspace / declared_source
    if declared_source.resolve() != source:
        report.errors.append("source_file and relative_path resolve to different files")
    if manifest.source_file_name != source.name:
        report.errors.append("source_file_name does not match source path")
    if manifest.file_extension != source.suffix.lower():
        report.errors.append("file_extension does not match source path")
    expected_mime = MIME_BY_EXTENSION.get(source.suffix.lower())
    if expected_mime is None:
        report.status = "unsupported"
        report.errors.append(f"unsupported source extension: {source.suffix.lower()}")
        return report
    if manifest.mime_type != expected_mime:
        report.errors.append(f"declared MIME {manifest.mime_type!r} does not match {expected_mime!r}")
    sniffed_mime = _sniff_mime(source)
    if sniffed_mime != expected_mime:
        report.errors.append(f"source signature/encoding does not match MIME {expected_mime!r}")
    if manifest.file_size != source.stat().st_size:
        report.errors.append("file_size does not match source")
    if manifest.sha256 != file_sha256(source):
        report.errors.append("sha256 does not match source")

    try:
        from modules.documents.ingest.registry import build_default_registry

        parser = build_default_registry().resolve(source, manifest.mime_type)
        if parser.__class__.__name__ != manifest.parser_selected:
            report.errors.append(
                f"parser_selected={manifest.parser_selected!r} but registry resolves {parser.__class__.__name__!r}"
            )
    except ValueError as exc:
        report.status = "unsupported"
        report.errors.append(str(exc))
        return report

    for kind, references in (
        ("ground truth", manifest.ground_truth_references),
        ("RAG questions", manifest.rag_question_references),
    ):
        for reference in references:
            target = _resolve_reference(corpus, reference.relative_path)
            if target is None:
                report.errors.append(f"{kind} reference escapes corpus root: {reference.relative_path}")
            elif not target.is_file():
                report.errors.append(f"{kind} reference is missing: {reference.relative_path}")
            elif file_sha256(target) != reference.sha256:
                report.errors.append(f"{kind} reference hash mismatch: {reference.relative_path}")

    expected_timestamp = GENERATOR_RELEASE_TIMESTAMPS.get(manifest.generator_version)
    if expected_timestamp and manifest.generation_timestamp != expected_timestamp:
        report.errors.append("generation_timestamp does not match the deterministic generator release timestamp")

    canonical_first = canonical_manifest_bytes(manifest)
    canonical_second = canonical_manifest_bytes(RawGoldenManifest.model_validate_json(canonical_first))
    report.byte_deterministic = canonical_first == canonical_second
    report.canonical_sha256 = hashlib.sha256(canonical_first).hexdigest()
    if not report.byte_deterministic:
        report.errors.append("canonical manifest serialization is not byte deterministic")
    if manifest_file.read_bytes() != canonical_first:
        report.errors.append("manifest file is not in canonical deterministic serialization")

    if report.errors and report.status not in {"manifest_failed", "unsupported"}:
        report.status = "manifest_conflict"
    if manifest.ground_truth_references and not manifest.ground_truth_independent:
        report.warnings.append("ground truth references are not independently verified; CER/WER is disabled")
    return report


def write_raw_manifest(destination: str | Path, manifest: RawGoldenManifest) -> None:
    """Write a new raw manifest without ever replacing an existing manifest."""

    if manifest.manifest_status != "raw_generated":
        raise ValueError("only raw_generated manifests can be written by this helper")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_manifest_bytes(manifest))

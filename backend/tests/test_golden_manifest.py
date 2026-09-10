from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from modules.documents.ingest.manifest import (
    GENERATOR_RELEASE_TIMESTAMPS,
    RawGoldenManifest,
    canonical_manifest_bytes,
    validate_manifest_file,
    write_raw_manifest,
)


GENERATOR_VERSION = "qbank-raw-manifest/2026-09-04.1"


def _payload(workspace: Path, corpus: Path, *, status: str = "raw_generated") -> dict:
    source = corpus / "text" / "fixture.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Dữ liệu kiểm thử UTF-8.", encoding="utf-8")
    relative_source = source.relative_to(workspace).as_posix()
    return {
        "manifest_version": "1.0.0",
        "manifest_status": status,
        "requires_human_review": status == "raw_generated",
        "fixture_id": "text-fixture",
        "source_file": relative_source,
        "source_file_name": source.name,
        "relative_path": source.relative_to(corpus).as_posix(),
        "file_extension": ".txt",
        "mime_type": "text/plain",
        "file_size": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "language_detected": "vi",
        "document_category": "plain_text_utf8",
        "page_count": None,
        "source_unit_count": 1,
        "has_text_layer": None,
        "is_scanned": False,
        "is_mixed": False,
        "expected_content_types": ["prose"],
        "detected_code_locations": [],
        "detected_table_locations": [],
        "detected_formula_locations": [],
        "detected_image_or_diagram_locations": [],
        "ground_truth_available": False,
        "ground_truth_independent": False,
        "ground_truth_references": [],
        "rag_questions_available": False,
        "rag_question_references": [],
        "parser_selected": "TextParser",
        "extractor_strategy": "utf8_sig_decode",
        "detection_confidence": 1.0,
        "generator_version": GENERATOR_VERSION,
        "generation_timestamp": GENERATOR_RELEASE_TIMESTAMPS[GENERATOR_VERSION],
        "eligible_for_cer_wer": False,
        "detection_evidence": {"encoding_probe": "utf-8-sig_success"},
        "warnings": ["requires review"],
    }


def _write_manifest(path: Path, payload: dict) -> None:
    manifest = RawGoldenManifest.model_validate(payload)
    write_raw_manifest(path, manifest)


def test_raw_manifest_validates_hash_mime_reference_parser_and_determinism(tmp_path: Path):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus)
    truth = corpus / "ground-truth" / "truth.txt"
    truth.parent.mkdir(parents=True)
    truth.write_text("Dữ liệu kiểm thử UTF-8.", encoding="utf-8")
    payload.update(
        {
            "ground_truth_available": True,
            "ground_truth_independent": True,
            "ground_truth_references": [
                {
                    "relative_path": truth.relative_to(corpus).as_posix(),
                    "sha256": hashlib.sha256(truth.read_bytes()).hexdigest(),
                    "status": "author_before_render",
                }
            ],
            "eligible_for_cer_wer": True,
        }
    )
    manifest_path = corpus / "manifests" / "raw-generated" / "fixture.json"
    _write_manifest(manifest_path, payload)

    report = validate_manifest_file(manifest_path, corpus_root=corpus, workspace_root=tmp_path)

    assert report.status == "raw_generated"
    assert report.valid is True
    assert report.byte_deterministic is True
    parsed = RawGoldenManifest.model_validate_json(manifest_path.read_bytes())
    assert canonical_manifest_bytes(parsed) == canonical_manifest_bytes(parsed)
    assert manifest_path.read_bytes() == canonical_manifest_bytes(parsed)


@pytest.mark.parametrize("field", ["source_file", "mime_type", "sha256", "parser_selected"])
def test_required_manifest_fields_are_enforced(tmp_path: Path, field: str):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus)
    payload.pop(field)

    with pytest.raises(ValidationError):
        RawGoldenManifest.model_validate(payload)


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("mime_type", "application/pdf")])
def test_source_conflict_is_reported(tmp_path: Path, field: str, value: str):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus)
    payload[field] = value
    manifest_path = corpus / "manifests" / "raw-generated" / "fixture.json"
    _write_manifest(manifest_path, payload)

    report = validate_manifest_file(manifest_path, corpus_root=corpus, workspace_root=tmp_path)

    assert report.status == "manifest_conflict"
    assert report.valid is False


def test_missing_reference_is_reported(tmp_path: Path):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus)
    payload.update(
        {
            "ground_truth_available": True,
            "ground_truth_independent": True,
            "ground_truth_references": [
                {"relative_path": "ground-truth/missing.txt", "sha256": "1" * 64}
            ],
            "eligible_for_cer_wer": True,
        }
    )
    manifest_path = corpus / "manifests" / "raw-generated" / "fixture.json"
    _write_manifest(manifest_path, payload)

    report = validate_manifest_file(manifest_path, corpus_root=corpus, workspace_root=tmp_path)

    assert report.status == "manifest_conflict"
    assert "reference is missing" in " ".join(report.errors)


@pytest.mark.parametrize(
    ("status", "expected_valid"),
    [
        ("verified", True),
        ("raw_generated", True),
        ("manifest_conflict", False),
        ("manifest_failed", False),
        ("unsupported", False),
    ],
)
def test_all_manifest_states_are_explicit(tmp_path: Path, status: str, expected_valid: bool):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus, status=status)
    manifest_path = corpus / "manifests" / "raw-generated" / f"{status}.json"
    _write_manifest(manifest_path, payload) if status == "raw_generated" else manifest_path.parent.mkdir(
        parents=True, exist_ok=True
    )
    if status != "raw_generated":
        model = RawGoldenManifest.model_validate(payload)
        manifest_path.write_bytes(canonical_manifest_bytes(model))

    report = validate_manifest_file(manifest_path, corpus_root=corpus, workspace_root=tmp_path)

    assert report.status == status
    assert report.valid is expected_valid


def test_cer_wer_requires_independent_ground_truth(tmp_path: Path):
    corpus = tmp_path / "golden-corpus"
    payload = _payload(tmp_path, corpus)
    payload["eligible_for_cer_wer"] = True

    with pytest.raises(ValidationError, match="CER/WER requires"):
        RawGoldenManifest.model_validate(payload)


def test_writer_never_overwrites_an_existing_manifest(tmp_path: Path):
    corpus = tmp_path / "golden-corpus"
    manifest = RawGoldenManifest.model_validate(_payload(tmp_path, corpus))
    destination = corpus / "manifests" / "raw-generated" / "fixture.json"
    write_raw_manifest(destination, manifest)

    with pytest.raises(FileExistsError):
        write_raw_manifest(destination, manifest)

    assert json.loads(destination.read_text(encoding="utf-8"))["manifest_status"] == "raw_generated"

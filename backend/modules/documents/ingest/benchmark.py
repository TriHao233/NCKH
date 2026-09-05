from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable
import json
from pathlib import Path


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value or "")


def _distance(left: list[str] | str, right: list[str] | str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_item in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(expected: str, actual: str) -> float:
    expected_nfc, actual_nfc = _nfc(expected), _nfc(actual)
    return _distance(expected_nfc, actual_nfc) / max(len(expected_nfc), 1)


def word_error_rate(expected: str, actual: str) -> float:
    expected_words = re.findall(r"\S+", _nfc(expected))
    actual_words = re.findall(r"\S+", _nfc(actual))
    return _distance(expected_words, actual_words) / max(len(expected_words), 1)


def _strip_accents(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    return "".join(char for char in unicodedata.normalize("NFD", value) if not unicodedata.combining(char))


def _normalize_text_for_accuracy(value: str) -> str:
    """Ignore representational whitespace/Markdown table rules, but preserve source words and symbols."""
    visible_lines: list[str] = []
    for line in _nfc(value).splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        visible_lines.append(line.replace("|", " "))
    return re.sub(r"\s+", " ", "\n".join(visible_lines)).strip()


def accent_error_rate(expected: str, actual: str) -> float:
    expected_words = re.findall(r"[^\W_]+", _nfc(expected), flags=re.UNICODE)
    actual_words = re.findall(r"[^\W_]+", _nfc(actual), flags=re.UNICODE)
    comparable = 0
    errors = 0
    for expected_word, actual_word in zip(expected_words, actual_words):
        if _strip_accents(expected_word).casefold() == _strip_accents(actual_word).casefold():
            comparable += 1
            errors += expected_word != actual_word
    return errors / max(comparable, 1)


def _exact_ratio(expected: Iterable[Any], actual: Iterable[Any]) -> float:
    expected_list, actual_list = list(expected), list(actual)
    matched = sum(left == right for left, right in zip(expected_list, actual_list))
    return matched / max(len(expected_list), len(actual_list), 1)


def _normalized_formula(value: str) -> str:
    return re.sub(r"\s+", " ", _nfc(value)).strip().rstrip(".;:")


@dataclass(frozen=True)
class GoldenThreshold:
    cer: float
    no_missing_nonempty_pages: bool = True


THRESHOLDS = {
    "born_digital": GoldenThreshold(cer=0.01),
    "standard_scan": GoldenThreshold(cer=0.03),
    "degraded_scan": GoldenThreshold(cer=0.03),
    "structured_document": GoldenThreshold(cer=0.01),
}


def load_golden_case(corpus_dir: str | Path, case_id: str) -> tuple[dict, list[dict]]:
    root = Path(corpus_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    truth = json.loads((root / manifest["ground_truth"]).read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item["id"] == case_id), None)
    if not case:
        raise KeyError(case_id)
    by_number = {int(page["page_number"]): page for page in truth["pages"]}
    expected = []
    for local_number, truth_number in enumerate(case["pages"], start=1):
        expected.append({**by_number[int(truth_number)], "page_number": local_number})
    return case, expected


def evaluate_golden_case(expected_pages: list[dict], actual_pages: list[dict], profile: str) -> dict:
    if profile not in THRESHOLDS:
        raise ValueError(f"Unknown golden threshold profile: {profile}")
    actual_by_number = {int(page.get("page_number") or page.get("unit_number")): page for page in actual_pages}
    expected_text_parts: list[str] = []
    actual_text_parts: list[str] = []
    missing_nonempty_pages: list[int] = []
    expected_code: list[str] = []
    actual_code: list[str] = []
    expected_formulae: list[str] = []
    actual_formulae: list[str] = []
    expected_cells: list[str] = []
    actual_cells: list[str] = []
    expected_merges: list[tuple[int, int, int, int]] = []
    actual_merges: list[tuple[int, int, int, int]] = []
    expected_assets = 0
    actual_assets = 0
    expected_asset_types: list[str] = []
    actual_asset_types: list[str] = []
    valid_asset_provenance = 0
    formula_review_count = 0
    single_char_expected: list[str] = []
    single_char_actual: list[str] = []
    for expected in expected_pages:
        page_number = int(expected["page_number"])
        actual = actual_by_number.get(page_number) or {}
        expected_source_text = str(expected.get("text") or "")
        expected_captions = [
            str(asset.get("caption") or "").strip()
            for asset in expected.get("assets") or []
            if str(asset.get("caption") or "").strip()
        ]
        for caption in expected_captions:
            if _normalize_text_for_accuracy(caption) not in _normalize_text_for_accuracy(expected_source_text):
                expected_source_text += f"\n\n{caption}"
        expected_text = _normalize_text_for_accuracy(expected_source_text)
        actual_text = _normalize_text_for_accuracy(actual.get("text") or actual.get("cleaned_text") or "")
        expected_text_parts.append(expected_text)
        actual_text_parts.append(actual_text)
        if expected_text.strip() and not actual_text.strip():
            missing_nonempty_pages.append(page_number)
        blocks = actual.get("content_blocks") or []
        expected_code.extend(expected.get("code_lines") or [])
        actual_code.extend(
            line for block in blocks if block.get("block_type") == "code" for line in (block.get("content") or "").splitlines()
        )
        expected_formulae.extend(expected.get("formulae") or [])
        actual_formulae.extend(
            (block.get("structured_content") or {}).get("raw") or block.get("content") or ""
            for block in blocks
            if block.get("block_type") == "formula"
        )
        formula_review_count += sum(
            block.get("validation_status") == "needs_review"
            for block in blocks
            if block.get("block_type") == "formula"
        )
        expected_cells.extend(cell for table in expected.get("tables") or [] for row in table.get("rows") or [] for cell in row)
        expected_merges.extend(
            (
                int(merge["row"]),
                int(merge["column"]),
                int(merge.get("row_span", 1)),
                int(merge.get("column_span", 1)),
            )
            for table in expected.get("tables") or []
            for merge in table.get("merged_cells") or []
        )
        actual_cells.extend(
            str(cell)
            for block in blocks
            if block.get("block_type") == "table"
            for row in ((block.get("structured_content") or {}).get("rows") or [])
            for cell in row
        )
        actual_merges.extend(
            (
                int(cell.get("row", 0)),
                int(cell.get("column", 0)),
                int(cell.get("row_span", 1)),
                int(cell.get("column_span", 1)),
            )
            for block in blocks
            if block.get("block_type") == "table"
            for cell in ((block.get("structured_content") or {}).get("cells") or [])
            if int(cell.get("row_span", 1)) > 1 or int(cell.get("column_span", 1)) > 1
        )
        expected_page_assets = expected.get("assets") or []
        expected_assets += len(expected_page_assets)
        expected_asset_types.extend(str(asset.get("type") or "unknown") for asset in expected_page_assets)
        page_assets = [
            asset
            for asset in actual.get("assets") or []
            if not (asset.get("metadata") or {}).get("is_page_raster")
            or asset.get("asset_type") == "diagram"
            or bool(asset.get("source_caption"))
        ]
        actual_assets += len(page_assets)
        actual_asset_types.extend(str(asset.get("asset_type") or "unknown") for asset in page_assets)
        valid_asset_provenance += sum(
            bool(
                asset.get("content_sha256")
                and (asset.get("storage_uri") or (asset.get("provenance") or {}).get("raw_ref"))
                and (
                    (asset.get("provenance") or {}).get("page_number") is not None
                    or (asset.get("provenance") or {}).get("source_location")
                )
            )
            for asset in page_assets
        )
        single_char_expected.extend(re.findall(r"(?<!\w)[A-Za-zĐđ](?!\w)", expected_text))
        single_char_actual.extend(re.findall(r"(?<!\w)[A-Za-zĐđ](?!\w)", actual_text))
    expected_text = "\n\f\n".join(expected_text_parts)
    actual_text = "\n\f\n".join(actual_text_parts)
    cer = character_error_rate(expected_text, actual_text)
    threshold = THRESHOLDS[profile]
    code_line_accuracy = _exact_ratio(expected_code, actual_code) if expected_code else 1.0
    table_cell_accuracy = _exact_ratio(expected_cells, actual_cells) if expected_cells else 1.0
    expected_formulae_normalized = [_normalized_formula(item) for item in expected_formulae]
    actual_formulae_normalized = [_normalized_formula(item) for item in actual_formulae]
    formula_accuracy = (
        _exact_ratio(expected_formulae_normalized, actual_formulae_normalized) if expected_formulae else 1.0
    )
    formula_preserved_or_reviewed = min(
        1.0,
        (
            sum(
                any(expected_item in actual_item or actual_item in expected_item for actual_item in actual_formulae_normalized)
                for expected_item in expected_formulae_normalized
            )
            + formula_review_count
        )
        / max(len(expected_formulae), 1),
    ) if expected_formulae else 1.0
    expected_type_counts = Counter(expected_asset_types)
    actual_type_counts = Counter(actual_asset_types)
    matched_asset_types = sum(
        min(expected_count, actual_type_counts[asset_type])
        for asset_type, expected_count in expected_type_counts.items()
    )
    semantic_assets_ok = (
        not expected_assets
        or (
            matched_asset_types == expected_assets
            and matched_asset_types == actual_assets
            and valid_asset_provenance == actual_assets
        )
    )
    protected_structure_ok = (
        code_line_accuracy == 1.0
        and table_cell_accuracy == 1.0
        and formula_preserved_or_reviewed == 1.0
        and semantic_assets_ok
    )
    expected_code_symbols = [symbol for line in expected_code for symbol in re.findall(r"[^\w\s]", line)]
    actual_code_symbols = [symbol for line in actual_code for symbol in re.findall(r"[^\w\s]", line)]
    expected_indents = [len(line) - len(line.lstrip(" \t")) for line in expected_code]
    actual_indents = [len(line) - len(line.lstrip(" \t")) for line in actual_code]
    if missing_nonempty_pages:
        status = "failed"
    elif cer <= threshold.cer and protected_structure_ok:
        status = "passed"
    else:
        status = "needs_review"
    return {
        "status": status,
        "profile": profile,
        "thresholds": {
            "cer": threshold.cer,
            "no_missing_nonempty_pages": True,
            "text_normalization": (
                "NFC + collapsed whitespace + Markdown table delimiter removal + labeled source captions"
            ),
        },
        "metrics": {
            "cer": round(cer, 6),
            "wer": round(word_error_rate(expected_text, actual_text), 6),
            "accent_error_rate": round(accent_error_rate(expected_text, actual_text), 6),
            "page_recall": round((len(expected_pages) - len(missing_nonempty_pages)) / max(len(expected_pages), 1), 6),
            "missing_nonempty_pages": missing_nonempty_pages,
            "single_character_accuracy": round(_exact_ratio(single_char_expected, single_char_actual), 6),
            "code_line_exact_accuracy": round(code_line_accuracy, 6) if expected_code else None,
            "code_symbol_accuracy": round(_exact_ratio(expected_code_symbols, actual_code_symbols), 6)
            if expected_code else None,
            "code_indentation_accuracy": round(_exact_ratio(expected_indents, actual_indents), 6)
            if expected_code else None,
            "table_cell_accuracy": round(table_cell_accuracy, 6) if expected_cells else None,
            "table_row_column_order_accuracy": round(table_cell_accuracy, 6) if expected_cells else None,
            "table_merge_accuracy": round(_exact_ratio(expected_merges, actual_merges), 6)
            if expected_merges else None,
            "formula_exact_accuracy": round(formula_accuracy, 6) if expected_formulae else None,
            "formula_preserved_or_needs_review": round(formula_preserved_or_reviewed, 6)
            if expected_formulae else None,
            "asset_recall": round(matched_asset_types / max(expected_assets, 1), 6) if expected_assets else None,
            "asset_type_precision": round(matched_asset_types / max(actual_assets, 1), 6)
            if expected_assets else None,
            "asset_provenance_valid_rate": round(valid_asset_provenance / max(actual_assets, 1), 6)
            if expected_assets else None,
        },
    }


def evaluate_retrieval_cases(cases: list[dict], results_by_case: dict[str, dict]) -> dict:
    """Evaluate grounded retrieval and abstention without treating model prose as source truth."""
    reciprocal_ranks: list[float] = []
    answerable_hits = 0
    provenance_complete = 0
    provenance_total = 0
    abstention_passed = 0
    abstention_total = 0
    details = []
    for case in cases:
        observed = results_by_case.get(case["id"]) or {}
        results = observed.get("results") or []
        relevant_pages = set(case.get("relevant_truth_pages") or [])
        first_rank = None
        required_types = set(case.get("required_block_types") or [])
        required_assets = set(case.get("required_asset_types") or [])
        evidence_text = " ".join(
            [str(observed.get("answer") or "")]
            + [str(result.get("content") or result.get("content_excerpt") or "") for result in results[:5]]
        ).casefold()
        evidence_supported = all(
            str(required).casefold() in evidence_text for required in case.get("required_evidence") or []
        )
        for rank, result in enumerate(results[:5], start=1):
            result_pages = set(result.get("page_marks") or [])
            if not result_pages:
                page_start, page_end = result.get("page_start"), result.get("page_end")
                if page_start is not None and page_end is not None:
                    result_pages = set(range(int(page_start), int(page_end) + 1))
            result_types = {
                item
                for item in str(result.get("source_block_types") or result.get("content_type") or "").split(",")
                if item
            }
            result_assets = {
                item for item in str(result.get("source_asset_types") or "").split(",") if item
            }
            type_match = not required_types or bool(required_types & result_types)
            asset_match = not required_assets or bool(required_assets & result_assets)
            if relevant_pages & result_pages and type_match and asset_match and first_rank is None:
                first_rank = rank
            provenance_total += 1
            provenance_complete += bool(
                result.get("chunk_id")
                and result.get("source_uri")
                and (result_pages or result.get("source_locations"))
            )
        if case.get("answerable"):
            grounded_hit = first_rank is not None and evidence_supported
            answerable_hits += grounded_hit
            reciprocal_ranks.append(1.0 / first_rank if grounded_hit else 0.0)
        else:
            abstention_total += 1
            abstention_passed += bool(observed.get("abstained"))
        details.append(
            {
                "case_id": case["id"],
                "hit_at_5": bool(first_rank and evidence_supported) if case.get("answerable") else None,
                "reciprocal_rank": 1.0 / first_rank if first_rank and evidence_supported else 0.0
                if case.get("answerable") else None,
                "evidence_supported": evidence_supported if case.get("answerable") else None,
                "abstained": bool(observed.get("abstained")) if not case.get("answerable") else None,
            }
        )
    answerable_total = sum(bool(case.get("answerable")) for case in cases)
    return {
        "hit_at_5": answerable_hits / max(answerable_total, 1),
        "mrr": sum(reciprocal_ranks) / max(len(reciprocal_ranks), 1),
        "provenance_completeness": provenance_complete / max(provenance_total, 1),
        "abstention_accuracy": abstention_passed / max(abstention_total, 1),
        "details": details,
    }

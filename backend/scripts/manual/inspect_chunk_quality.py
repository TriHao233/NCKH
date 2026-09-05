"""Inspect a completed isolated audit run; no database/service access."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.rag.retrieval_policy import filter_retrieval_pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    with gzip.open(run / "extraction.raw.json.gz", "rt", encoding="utf-8") as handle:
        parsed = json.load(handle)
    metadata_file = next((run / "metadata").glob("*.json"))
    chunks = json.loads(metadata_file.read_text(encoding="utf-8"))["chunks"]
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    units = filter_retrieval_pages(parsed["units"]) if "retrieval_filter" in summary else parsed["units"]
    blocks = {b["block_id"]: b for u in units for b in u["content_blocks"]}
    anomalies = []
    toc = []
    headings = []
    boundaries = []
    sizes = []
    examples = []
    for index, chunk in enumerate(chunks):
        text = chunk["content"]
        meta = chunk["metadata"]
        sizes.append(len(text))
        if re.search(r"\.{3,}\s*\d+", text):
            toc.append(chunk["chunk_id"])
        source_blocks = [blocks[b] for b in meta.get("block_ids", []) if b in blocks]
        if source_blocks and all(b["block_type"] == "heading" for b in source_blocks):
            headings.append(chunk["chunk_id"])
        # Indicators, not a Vietnamese dictionary: valid single-letter words can
        # also match. Report for review; never auto-replace or discard them.
        single = [m.group() for m in re.finditer(r"(?<!\w)[^\W\d_](?!\w)", text)
                  if ord(m.group()) > 127]
        if single:
            anomalies.append({"chunk_id": chunk["chunk_id"], "pages": meta["page_marks"],
                              "single_accented_tokens": len(single), "examples": single[:8]})
        source = re.sub(r"\s+", " ", "\n\n".join(b["content"] for b in source_blocks))
        normalized = re.sub(r"\s+", " ", text).strip()
        start = source.find(normalized[:80])
        end_start = source.rfind(normalized[-80:])
        end = end_start + min(80, len(normalized))
        midword_start = start > 0 and source[start - 1].isalnum() and normalized[0].isalnum()
        midword_end = end_start >= 0 and end < len(source) and source[end].isalnum() and normalized[-1].isalnum()
        boundaries.append({
            "chunk_id": chunk["chunk_id"], "next_chunk_id": chunks[index + 1]["chunk_id"] if index + 1 < len(chunks) else None,
            "pages": meta["page_marks"], "source_start_found": start >= 0, "source_end_found": end_start >= 0,
            "midword_start": midword_start, "midword_end": midword_end,
            "start": text[:100], "end": text[-100:],
        })
        if len(text) < 120 or index in {0, len(chunks) // 2, len(chunks) - 1}:
            examples.append({"chunk_id": chunk["chunk_id"], "pages": meta["page_marks"],
                             "type": meta["content_type"], "heading": meta["heading"], "text": text})
    result = {
        "boundary_source_view": "retrieval-filtered blocks" if "retrieval_filter" in summary else "original blocks",
        "chunks": len(chunks), "characters": {"min": min(sizes), "average": round(sum(sizes) / len(sizes), 2), "max": max(sizes)},
        "types": dict(Counter(c["metadata"]["content_type"] for c in chunks)),
        "toc_pattern_chunks": toc, "heading_only_chunks": headings,
        "suspicious_single_accented_tokens": sum(a["single_accented_tokens"] for a in anomalies),
        "suspicious_chunks": anomalies,
        "non_nfc_chunks": sum(unicodedata.normalize("NFC", c["content"]) != c["content"] for c in chunks),
        "boundary_count": max(len(chunks) - 1, 0),
        "midword_boundary_flags": sum(b["midword_start"] or b["midword_end"] for b in boundaries),
        "unmatched_boundary_chunks": sum(not b["source_start_found"] or not b["source_end_found"] for b in boundaries),
        "boundaries": boundaries, "examples": examples,
    }
    (run / "quality-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"boundaries", "examples", "suspicious_chunks"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

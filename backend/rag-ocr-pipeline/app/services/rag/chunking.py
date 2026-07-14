import hashlib
import logging
import re
import unicodedata
from collections import Counter
from typing import Iterable

from app.core.config import settings
from app.db.mongodb import get_document_record, iter_document_pages, update_chunking_status, get_active_keywords
from app.engine.chromadb_engine import store_chunks
from app.models.chunking import ChunkingStats, DocumentChunkResponse
from app.utils.chunking_export import export_chunks_to_file

logger = logging.getLogger(__name__)

PAGE_MARKER_PATTERN = re.compile(r"<!--\s*PAGE:(\d+)\s*-->")
CODE_BLOCK_PATTERN = re.compile(r"```[^\n]*\n[\s\S]*?```")
FORMULA_BLOCK_PATTERN = re.compile(r"<FORMULA_BLOCK[\s\S]*?</FORMULA_BLOCK>")
LATEX_BLOCK_PATTERN = re.compile(r"\$\$[\s\S]*?\$\$")
TABLE_BLOCK_PATTERN = re.compile(r"(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)")
HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

TOP_LEVEL_PATTERNS = [
	re.compile(r"^#\s+.+$"),
	re.compile(r"^(CHUONG|CHAPTER|PHAN|BAI)\s+([IVX0-9]+)\b"),
]

SUB_LEVEL_2_PATTERN = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)[\.\s]+", re.IGNORECASE)
SUB_LEVEL_3_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?[\.\s]+")

BIG_O_PATTERN = re.compile(r"\bO\([^)]*\)")
EXAMPLE_PATTERN = re.compile(r"\b(thí dụ|ví dụ|vd)\b", re.IGNORECASE)
EXERCISE_PATTERN = re.compile(r"\b(bài tập|câu hỏi|thực hành|luyện tập|ôn tập)\b", re.IGNORECASE)
DEFINITION_PATTERN = re.compile(r"\b(định nghĩa|khái niệm|là gì)\b", re.IGNORECASE)

def chunk_document_and_store(
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
    collection_name: str | None = None,
    buffer_max_pages: int | None = None,
    buffer_max_chars: int | None = None,
    max_code_block_lines: int | None = None,
    dry_run: bool = False,
) -> DocumentChunkResponse:
    doc = get_document_record(document_id)
    if not doc:
        raise ValueError("Document not found")

    resolved_buffer_pages = buffer_max_pages or settings.chunk_buffer_max_pages
    resolved_buffer_chars = buffer_max_chars or settings.chunk_buffer_max_chars
    resolved_code_lines = max_code_block_lines or settings.max_code_block_lines

    update_chunking_status(document_id, status="processing")

    total_chunks = 0
    stored_chunks = 0
    original_length = 0
    total_chars = 0
    min_chunk = None
    max_chunk = 0
    content_type_distribution: Counter[str] = Counter()

    batch_ids: list[str] = []
    batch_docs: list[str] = []
    batch_metas: list[dict] = []
    
    # Mảng lưu trữ toàn bộ chunk để xuất file JSON & Markdown
    all_chunks_for_export = [] 

    for buffer_text, source_len in _iter_chapter_buffers(
        document_id,
        resolved_buffer_pages,
        resolved_buffer_chars,
    ):
        original_length += source_len
        for chunk in _chunk_buffer(
            buffer_text,
            document_id,
            chunk_size,
            chunk_overlap,
            resolved_code_lines,
        ):
            content = chunk["content"]
            metadata = chunk["metadata"]
            
            # Đẩy vào mảng export
            all_chunks_for_export.append(chunk)

            total_chunks += 1
            char_count = len(content)
            total_chars += char_count
            min_chunk = char_count if min_chunk is None else min(min_chunk, char_count)
            max_chunk = max(max_chunk, char_count)
            content_type_distribution[metadata.get("content_type", "text")] += 1

            if dry_run:
                continue

            batch_ids.append(chunk["chunk_id"])
            batch_docs.append(content)
            batch_metas.append(metadata)

            if len(batch_ids) >= settings.chromadb_batch_size:
                stored_chunks += store_chunks(batch_ids, batch_docs, batch_metas, collection_name)
                batch_ids.clear()
                batch_docs.clear()
                batch_metas.clear()

    if not dry_run and batch_ids:
        stored_chunks += store_chunks(batch_ids, batch_docs, batch_metas, collection_name)

    avg_chunk = round(total_chars / max(total_chunks, 1), 2)
    stats = ChunkingStats(
        original_length=original_length,
        total_chunks=total_chunks,
        junk_removed=0,
        avg_chunk_size=avg_chunk,
        min_chunk_size=min_chunk or 0,
        max_chunk_size=max_chunk,
        content_type_distribution=dict(content_type_distribution),
    )

    update_chunking_status(
        document_id,
        status="completed" if not dry_run else "dry_run",
        stats=stats.model_dump(),
        collection_name=collection_name or settings.chromadb_collection_name,
        total_chunks=total_chunks,
        stored_chunks=stored_chunks,
    )

    # THỰC HIỆN XUẤT FILE SAU KHI ĐÃ CẮT XONG (Bao gồm cả dry_run và real run)
    if all_chunks_for_export:
        try:
            export_chunks_to_file(document_id, all_chunks_for_export)
        except Exception as e:
            logger.error(f"Lỗi khi xuất file metadata: {e}")

    return DocumentChunkResponse(
        document_id=document_id,
        collection_name=collection_name or settings.chromadb_collection_name,
        total_chunks=total_chunks,
        stored_chunks=stored_chunks,
        stats=stats,
    )


def _iter_chapter_buffers(
	document_id: str,
	buffer_max_pages: int,
	buffer_max_chars: int,
) -> Iterable[tuple[str, int]]:
	buffer_lines: list[str] = []
	buffer_pages = 0
	buffer_chars = 0
	buffer_source_len = 0

	for page in iter_document_pages(document_id):
		page_text = page.get("text", "") or ""
		page_number = page.get("page_number", 0)
		marker = f"<!-- PAGE:{page_number} -->"

		if not buffer_lines:
			buffer_lines.append(marker)
		else:
			buffer_lines.append(marker)

		lines = page_text.splitlines() if page_text else []
		for line in lines:
			normalized_line = _smart_normalize_heading(line)
			if normalized_line.startswith("# "):
				if _buffer_has_content(buffer_lines):
					yield "\n".join(buffer_lines).strip(), buffer_source_len
					buffer_lines = [marker]
					buffer_pages = 0
					buffer_chars = 0
					buffer_source_len = 0

			buffer_lines.append(normalized_line)
			buffer_chars += len(normalized_line) + 1

		buffer_pages += 1
		buffer_source_len += len(page_text)

		if buffer_pages >= buffer_max_pages or buffer_chars >= buffer_max_chars:
			yield "\n".join(buffer_lines).strip(), buffer_source_len
			buffer_lines = []
			buffer_pages = 0
			buffer_chars = 0
			buffer_source_len = 0

	if buffer_lines:
		yield "\n".join(buffer_lines).strip(), buffer_source_len


def _chunk_buffer(
	text: str,
	document_id: str,
	chunk_size: int,
	chunk_overlap: int,
	max_code_block_lines: int,
) -> Iterable[dict]:
	sections = _split_by_markdown_headers(text)
	chunk_index = 0

	# LẤY TỪ KHÓA ĐỘNG TỪ MONGODB (Chỉ gọi 1 lần cho cả Buffer giúp tối ưu performance)
	dynamic_keywords = get_active_keywords(course_id="it_fundamentals")

	for section in sections:
		masked_text, protected = _mask_blocks(section["content"], max_code_block_lines)
		parts = _split_recursive(masked_text, chunk_size, chunk_overlap)

		for part in parts:
			restored = _restore_blocks(part, protected)
			page_marks = _extract_page_marks(restored)
			clean_text = _strip_page_markers(restored)
			if not clean_text.strip():
				continue

			chunk_index += 1
			token_count = _count_tokens(clean_text)

			# TRUYỀN TỪ KHÓA ĐỘNG VÀO HÀM TÍNH DENSITY
			keyword_hits, density = _information_density(clean_text, token_count, dynamic_keywords)
			semantic = _detect_semantic_type(clean_text, section["heading"])
			heading_path_text = " > ".join(section["heading_path"]) if section["heading_path"] else ""
			heading_norm = _normalize_heading_meta(section["heading"]) if section["heading"] else ""
			heading_path_norm = _normalize_heading_meta(heading_path_text) if heading_path_text else ""

			metadata = {
				"document_id": document_id,
				"heading_path": section["heading_path"],
				"heading": section["heading"],
				"heading_path_text": heading_path_text,
				"heading_norm": heading_norm,
				"heading_path_norm": heading_path_norm,
				"page_start": page_marks["page_start"],
				"page_end": page_marks["page_end"],
				"page_marks": page_marks["pages"],
				"content_type": _detect_content_type(clean_text),
				"semantic_type": semantic,
				"keyword_hits": keyword_hits,
				"information_density": density,
				"token_count": token_count,
			}

			chunk_id = _generate_chunk_id(document_id, chunk_index, clean_text)
			yield {
				"chunk_id": chunk_id,
				"content": clean_text,
				"metadata": metadata,
			}


def _split_by_markdown_headers(text: str) -> list[dict]:
	matches = list(HEADING_PATTERN.finditer(text))
	if not matches:
		return [{"heading": "", "heading_path": [], "content": text}]

	sections: list[dict] = []
	if matches[0].start() > 0:
		pre = text[: matches[0].start()].strip()
		if pre:
			sections.append({"heading": "", "heading_path": [], "content": pre})

	heading_stack: list[str] = []
	for i, match in enumerate(matches):
		level = len(match.group(1))
		heading = match.group(2).strip()

		if level == 1:
			heading_stack = [heading]
		elif level == 2:
			heading_stack = heading_stack[:1] + [heading] if heading_stack else [heading]
		else:
			heading_stack = heading_stack[:2] + [heading] if heading_stack else [heading]

		body_start = match.end()
		body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
		body = text[body_start:body_end].strip()
		content = f"{match.group(0).strip()}\n\n{body}" if body else match.group(0).strip()

		sections.append(
			{
				"heading": heading,
				"heading_path": list(heading_stack),
				"content": content,
			}
		)

	return sections


def _strip_accents(text: str) -> str:
	normalized = unicodedata.normalize("NFKD", text)
	return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_heading_meta(value: str) -> str:
	if not value:
		return ""
	folded = _strip_accents(value)
	return re.sub(r"\s+", " ", folded).strip().lower()


def _is_heading_like_remainder(remainder: str) -> bool:
	"""Real Roman-numeral headings in this corpus are followed by ALL-CAPS
	Vietnamese text (e.g. "I TỪ BÀI TOÁN ĐẾN CHƯƠNG TRÌNH"). Single-letter
	numerals (I/V/X) also collide with common variable names in code/math
	sentences (e.g. "x giống như x = X + 1"), which are lowercase/mixed-case.
	Require the remainder to be substantially uppercase to reject those."""
	letters = [ch for ch in _strip_accents(remainder) if ch.isalpha()]
	if len(letters) < 3:
		return False
	return all(ch.isupper() for ch in letters)


def _smart_normalize_heading(line: str) -> str:
	stripped = line.strip()
	if not stripped:
		return stripped
	if stripped.startswith("#"):
		return stripped
	if len(stripped) > 100:
		return stripped

	folded = _strip_accents(stripped).upper()
	if any(pattern.match(folded) for pattern in TOP_LEVEL_PATTERNS):
		return f"# {stripped}"
	sub2_match = SUB_LEVEL_2_PATTERN.match(stripped)
	if sub2_match and _is_heading_like_remainder(stripped[sub2_match.end():]):
		return f"## {stripped}"
	if SUB_LEVEL_3_PATTERN.match(stripped):
		return f"### {stripped}"

	return stripped


def _buffer_has_content(lines: list[str]) -> bool:
	"""A buffer only counts as real content once it has body text, not just
	page markers or heading lines. Without this, a run of consecutive
	headings (e.g. a table-of-contents page listing every chapter title)
	each triggers a yield, producing near-empty chunks."""
	for line in lines:
		s = line.strip()
		if not s or PAGE_MARKER_PATTERN.match(s):
			continue
		if s.startswith("#"):
			continue
		return True
	return False


def _mask_blocks(text: str, max_code_block_lines: int) -> tuple[str, dict]:
	protected: dict[str, str] = {}
	counter = 0

	def _store(prefix: str, value: str) -> str:
		nonlocal counter
		key = f"__{prefix}_{counter}__"
		protected[key] = value
		counter += 1
		return key

	def _split_code_block(block: str) -> str:
		lines = block.splitlines()
		if len(lines) < 2:
			return _store("CODEBLOCK", block)

		fence = lines[0]
		lang = fence.replace("```", "").strip() or "cpp"
		code_lines = lines[1:-1]
		if len(code_lines) <= max_code_block_lines:
			return _store("CODEBLOCK", block)

		segments = []
		total = (len(code_lines) + max_code_block_lines - 1) // max_code_block_lines
		for idx in range(total):
			start = idx * max_code_block_lines
			end = min(start + max_code_block_lines, len(code_lines))
			seg_lines = code_lines[start:end]
			if idx > 0:
				seg_lines = ["// (Continuation of previous code block)"] + seg_lines
			if idx < total - 1:
				seg_lines = seg_lines + ["// (Continues in next code block)"]
			seg_block = f"```{lang}\n" + "\n".join(seg_lines) + "\n```"
			segments.append(_store("CODEBLOCK", seg_block))

		return "\n\n".join(segments)

	def _replace_code(match: re.Match) -> str:
		return _split_code_block(match.group())

	text = CODE_BLOCK_PATTERN.sub(_replace_code, text)
	text = FORMULA_BLOCK_PATTERN.sub(lambda m: _store("FORMULA", m.group()), text)
	text = LATEX_BLOCK_PATTERN.sub(lambda m: _store("LATEX", m.group()), text)
	text = TABLE_BLOCK_PATTERN.sub(lambda m: _store("TABLE", m.group()), text)

	return text, protected


def _restore_blocks(text: str, protected: dict) -> str:
	for key, value in protected.items():
		text = text.replace(key, value)
	return text


def _split_recursive(
	text: str,
	chunk_size: int,
	chunk_overlap: int,
	separators: list[str] | None = None,
) -> list[str]:
	if separators is None:
		separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

	sep = separators[-1]
	rest = []
	for i, s in enumerate(separators):
		if s == "":
			sep = s
			break
		if s in text:
			sep = s
			rest = separators[i + 1 :]
			break

	splits = text.split(sep) if sep else list(text)
	final: list[str] = []
	good: list[str] = []
	for part in splits:
		if len(part) < chunk_size:
			good.append(part)
		else:
			if good:
				final.extend(_merge(good, sep, chunk_size, chunk_overlap))
				good = []
			if not rest:
				final.append(part)
			else:
				final.extend(_split_recursive(part, chunk_size, chunk_overlap, rest))

	if good:
		final.extend(_merge(good, sep, chunk_size, chunk_overlap))

	return final


def _merge(splits: list[str], sep: str, chunk_size: int, chunk_overlap: int) -> list[str]:
	chunks: list[str] = []
	parts: list[str] = []
	cur_len = 0

	for part in splits:
		test = cur_len + len(part) + (len(sep) if parts else 0)
		if test > chunk_size and parts:
			t = sep.join(parts).strip()
			if t:
				chunks.append(t)
			while cur_len > chunk_overlap and len(parts) > 1:
				cur_len -= len(parts.pop(0)) + len(sep)

		parts.append(part)
		cur_len = sum(len(p) for p in parts) + len(sep) * (len(parts) - 1)

	if parts:
		t = sep.join(parts).strip()
		if t:
			chunks.append(t)

	return chunks


def _extract_page_marks(text: str) -> dict:
	pages = [int(m.group(1)) for m in PAGE_MARKER_PATTERN.finditer(text)]
	if pages:
		return {"pages": sorted(set(pages)), "page_start": min(pages), "page_end": max(pages)}
	return {"pages": [], "page_start": None, "page_end": None}


def _strip_page_markers(text: str) -> str:
	cleaned = PAGE_MARKER_PATTERN.sub("", text)
	cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
	return cleaned.strip()


def _generate_chunk_id(doc_id: str, index: int, content: str) -> str:
	raw = f"{doc_id}::{index}::{content}"
	return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _detect_content_type(text: str) -> str:
	has_code = "```" in text
	has_formula = "<FORMULA_BLOCK" in text or "$$" in text
	if has_code and has_formula:
		return "mixed"
	if has_code:
		return "code"
	if has_formula:
		return "formula"
	return "text"


def _detect_semantic_type(text: str, heading: str) -> str:
	context_to_check = f"{heading} {text[:200]}".strip().lower()
	if EXERCISE_PATTERN.search(context_to_check):
		return "exercise"
	if EXAMPLE_PATTERN.search(context_to_check):
		return "example"
	if DEFINITION_PATTERN.search(context_to_check):
		return "definition"
	return "theory"


def _count_tokens(text: str) -> int:
	# OLD: return len(re.findall(r"[A-Za-z0-9_]+", text))
	return len(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def _information_density(text: str, token_count: int, keywords: list[str]) -> tuple[int, float]:
	lowered = text.lower()
	hits = 0
	for kw in keywords:
		hits += len(re.findall(rf"\b{re.escape(kw)}\b", lowered))
	hits += len(BIG_O_PATTERN.findall(text))
	density = round(hits / max(token_count, 1), 4)
	return hits, density

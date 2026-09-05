import hashlib

from core.config import settings
from core.database import get_database
from modules.generation.prompt_loader import PromptLoader


class PromptBuilder:
    @staticmethod
    def _load_db_template(template_key: str) -> dict | None:
        return get_database().prompt_templates.find_one(
            {"template_key": template_key, "is_active": True},
            sort=[("version", -1)],
        )

    @staticmethod
    def _load_template(template_key: str, relative_path: str) -> tuple[str, dict]:
        if settings.prompt_source == "db":
            try:
                template = PromptBuilder._load_db_template(template_key)
            except Exception as exc:
                raise RuntimeError(
                    f"PROMPT_SOURCE_UNAVAILABLE: không đọc được template '{template_key}'"
                ) from exc
            if not template or not template.get("prompt_body"):
                raise RuntimeError(
                    f"PROMPT_TEMPLATE_NOT_FOUND: thiếu template DB đang hoạt động '{template_key}'"
                )
            body = str(template["prompt_body"])
            actual_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            recorded_hash = str(template.get("content_hash") or "")
            if recorded_hash and recorded_hash != actual_hash:
                raise RuntimeError(
                    f"PROMPT_TEMPLATE_HASH_MISMATCH: template '{template_key}'"
                )
            return body, {
                "template_key": template_key,
                "source": "db",
                "version": int(template.get("version") or 1),
                "content_hash": actual_hash,
                "template_id": str(template.get("_id") or "") or None,
            }

        body = PromptLoader.load(relative_path)
        return body, {
            "template_key": template_key,
            "source": "file",
            "version": "file",
            "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "relative_path": relative_path,
        }

    def build_with_manifest(
        self,
        context: str,
        bloom_level: str,
        question_type: str,
        num_questions: int,
        instruction: str | None = None,
        topic: str | None = None,
        avoid_questions: list[str] | None = None,
        learning_outcomes: list[dict] | None = None,
        content_mode: str = "general",
    ) -> dict:
        specs = [
            ("system", "system.txt"),
            ("question_rule", "question_rule.txt"),
            (f"bloom:{bloom_level}", f"bloom/{bloom_level}.txt"),
            ("quy_dinh_do_kho", "quy_dinh_do_kho.txt"),
            (f"question_type:{question_type}", f"question_type/{question_type}.txt"),
            (
                f"question_structure:{question_type}",
                f"question_structure/{question_type}.txt",
            ),
            ("output_format", "output_format.txt"),
        ]
        resolved = [self._load_template(key, path) for key, path in specs]
        (
            system,
            question_rule,
            bloom,
            difficulty_rule,
            qtype,
            qstructure,
            output,
        ) = [item[0] for item in resolved]
        manifest = [item[1] for item in resolved]

        topic_block = f"\nCHỦ ĐỀ TRỌNG TÂM:\n{topic.strip()}\n" if topic else ""
        instruction_block = ""
        if instruction:
            instruction_block = f"""
YÊU CẦU CỦA GIẢNG VIÊN:
{instruction.strip()}
Chỉ làm theo yêu cầu này khi có căn cứ trong NGỮ CẢNH và không xung đột với quy tắc bắt buộc hoặc schema đầu ra.
"""
        duplicate_block = ""
        if avoid_questions:
            avoid_list = "\n".join(
                f"- {question.strip()}"
                for question in avoid_questions[-12:]
                if question and question.strip()
            )
            if avoid_list:
                duplicate_block = f"""
TRÁNH TRÙNG LẶP:
Không lặp lại hoặc diễn đạt lại các câu hỏi đã có sau:
{avoid_list}
"""
        clo_block = ""
        if learning_outcomes:
            clo_lines = "\n".join(
                f"- {item['clo_code']}: {item['description']}"
                for item in learning_outcomes
                if item.get("clo_code") and item.get("description")
            )
            if clo_lines:
                clo_block = f"""
CHUẨN ĐẦU RA ĐƯỢC PHÉP:
{clo_lines}
Đặt `clo_codes` bằng mã phù hợp nhất trong danh sách này. Không tự tạo mã mới.
"""
        mode_block = (
            "CHẾ ĐỘ NỘI DUNG: CODE\nTạo câu hỏi đọc, truy vết, gỡ lỗi hoặc suy luận "
            "về mã nguồn có căn cứ trong NGỮ CẢNH. Chỉ thêm đoạn mã khi nguồn hỗ trợ."
            if content_mode == "code"
            else "CHẾ ĐỘ NỘI DUNG: LÝ THUYẾT\nƯu tiên kiến thức khái niệm và "
            "phi mã nguồn có căn cứ trong NGỮ CẢNH."
        )

        rendered_prompt = f"""
{system}
{question_rule}
{bloom}
{difficulty_rule}
{qtype}
{qstructure}

NHIỆM VỤ: Sinh chính xác {num_questions} câu hỏi.
{topic_block}
{instruction_block}
{duplicate_block}
{clo_block}
{mode_block}
NGỮ CẢNH:
{context}

QUY TẮC MINH CHỨNG:
- `source_context` phải chép nguyên văn từ phần sau `Nội dung:` trong NGỮ CẢNH; không dùng dòng `Mục lục:` làm minh chứng.
- Mỗi `source_keyword` phải xuất hiện nguyên văn trong cả `source_context` và nội dung câu hỏi.
- Dùng tối đa 2 `source_keyword` ngắn; dùng danh sách rỗng nếu không có từ khóa đáng tin cậy.
- Ưu tiên một câu minh chứng ngắn trực tiếp chứng minh đáp án đúng.

{output}
"""
        return {
            "rendered_prompt": rendered_prompt,
            "rendered_prompt_hash": hashlib.sha256(
                rendered_prompt.encode("utf-8")
            ).hexdigest(),
            "templates": manifest,
            "release_hash": hashlib.sha256(
                "|".join(
                    f"{item['template_key']}:{item['content_hash']}" for item in manifest
                ).encode("utf-8")
            ).hexdigest(),
        }

    def build(self, *args, **kwargs) -> str:
        return self.build_with_manifest(*args, **kwargs)["rendered_prompt"]

from modules.generation.prompt_loader import PromptLoader
from core.config import settings
from core.database import get_database

class PromptBuilder:
    @staticmethod
    def _load_db_template(template_key: str) -> str | None:
        try:
            template = get_database().prompt_templates.find_one(
                {"template_key": template_key, "is_active": True},
                sort=[("version", -1)],
            )
            if template and template.get("prompt_body"):
                return template["prompt_body"]
        except Exception:
            pass
        return None

    @staticmethod
    def _load_template(template_key: str, relative_path: str) -> str:
        if settings.prompt_source == "db":
            db_template = PromptBuilder._load_db_template(template_key)
            if db_template:
                return db_template
        return PromptLoader.load(relative_path)

    def build(
        self,
        context: str,
        bloom_level: str,
        question_type: str,
        num_questions: int,
        instruction: str | None = None,
        avoid_questions: list[str] | None = None,
        learning_outcomes: list[dict] | None = None,
        content_mode: str = "general",
    ):
        system = self._load_template("system", "system.txt")
        question_rule = self._load_template("question_rule", "question_rule.txt")
        bloom = self._load_template(f"bloom:{bloom_level}", f"bloom/{bloom_level}.txt")
        difficulty_rule = self._load_template("quy_dinh_do_kho", "quy_dinh_do_kho.txt")
        qtype = self._load_template(f"question_type:{question_type}", f"question_type/{question_type}.txt")
        qstructure = self._load_template(
            f"question_structure:{question_type}",
            f"question_structure/{question_type}.txt",
        )
        output = self._load_template("output_format", "output_format.txt")
        instruction_block = ""
        if instruction:
            instruction_block = f"""
TEACHER REQUEST:
{instruction.strip()}
Note: Follow this request only when it is grounded in CONTEXT and does not conflict with the critical rules or output schema.
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
AVOID DUPLICATES:
Do not repeat or paraphrase the following previously generated questions:
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
LEARNING OUTCOMES:
{clo_lines}
Set `clo_codes` to the best matching codes from this list. Do not invent codes.
"""
        mode_block = (
            "CONTENT MODE: CODE\nCreate questions that require reading, tracing, debugging, or reasoning about code "
            "grounded in CONTEXT. Include a code snippet only when CONTEXT supports it."
            if content_mode == "code"
            else "CONTENT MODE: GENERAL\nPrioritize conceptual and non-code knowledge grounded in CONTEXT."
        )

        # Ráp lại với cấu trúc tối ưu hóa
        return f"""
{system}
{question_rule}
{bloom}
{difficulty_rule}
{qtype}
{qstructure}

TASK: Generate exactly {num_questions} questions.
{instruction_block}
{duplicate_block}
{clo_block}
{mode_block}
CONTEXT:
{context}

EVIDENCE RULES:
- `source_context` must be copied verbatim only from text after `Nội dung:` in CONTEXT; never use a `Mục lục:` line as evidence.
- Every `source_keyword` must appear verbatim in both `source_context` and the question text.
- Use at most 2 short `source_keyword` values; use an empty list when no reliable keyword is needed.
- Prefer a concise evidence sentence that directly proves the correct answer.

{output}
"""

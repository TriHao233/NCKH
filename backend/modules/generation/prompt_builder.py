from modules.generation.prompt_loader import PromptLoader
from core.database import get_database

class PromptBuilder:
    @staticmethod
    def _load_template(template_key: str, relative_path: str) -> str:
        try:
            template = get_database().prompt_templates.find_one(
                {"template_key": template_key, "is_active": True},
                sort=[("version", -1)],
            )
            if template and template.get("prompt_body"):
                return template["prompt_body"]
        except Exception:
            pass
        return PromptLoader.load(relative_path)

    def build(
        self,
        context: str,
        bloom_level: str,
        question_type: str,
        num_questions: int,
        instruction: str | None = None,
        avoid_questions: list[str] | None = None,
    ):
        system = self._load_template("system", "system.txt")
        bloom = self._load_template(f"bloom:{bloom_level}", f"bloom/{bloom_level}.txt")
        qtype = self._load_template(f"question_type:{question_type}", f"question_type/{question_type}.txt")
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

        # Ráp lại với cấu trúc tối ưu hóa
        return f"""
{system}
{bloom}
{qtype}

TASK: Generate exactly {num_questions} questions.
{instruction_block}
{duplicate_block}
CONTEXT:
{context}

{output}
"""

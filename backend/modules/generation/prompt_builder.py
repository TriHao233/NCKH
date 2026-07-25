from modules.generation.prompt_loader import PromptLoader

class PromptBuilder:
    def build(
        self,
        context: str,
        bloom_level: str,
        question_type: str,
        num_questions: int,
        instruction: str | None = None,
        avoid_questions: list[str] | None = None,
    ):
        system = PromptLoader.load("system.txt")
        bloom = PromptLoader.load(f"bloom/{bloom_level}.txt")
        qtype = PromptLoader.load(f"question_type/{question_type}.txt")
        output = PromptLoader.load("output_format.txt")
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

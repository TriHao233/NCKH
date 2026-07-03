from app.services.generation.prompt_loader import PromptLoader

class PromptBuilder:
    def build(self, context: str, bloom_level: str, question_type: str, num_questions: int):
        system = PromptLoader.load("system.txt")
        bloom = PromptLoader.load(f"bloom/{bloom_level}.txt")
        qtype = PromptLoader.load(f"question_type/{question_type}.txt")
        example = PromptLoader.load("examples.txt") # Thêm dòng này
        output = PromptLoader.load("output_format.txt")

        # Ráp lại với cấu trúc tối ưu hóa
        return f"""
{system}
{bloom}
{qtype}
{example}

TASK: Generate exactly {num_questions} questions.
CONTEXT:
{context}

{output}
"""
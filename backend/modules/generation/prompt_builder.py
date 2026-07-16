from modules.generation.prompt_loader import PromptLoader

class PromptBuilder:
    def build(self, context: str, bloom_level: str, question_type: str, num_questions: int):
        system = PromptLoader.load("system.txt")
        bloom = PromptLoader.load(f"bloom/{bloom_level}.txt")
        qtype = PromptLoader.load(f"question_type/{question_type}.txt")
        # Ví dụ theo đúng loại câu đang sinh (mỗi loại có cấu trúc JSON khác nhau)
        example = PromptLoader.load(f"examples/{question_type}.txt")
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

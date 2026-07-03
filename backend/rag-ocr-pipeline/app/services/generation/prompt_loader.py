from pathlib import Path

PROMPT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "prompts"
)

class PromptLoader:

    @staticmethod
    def load(relative_path: str) -> str:
        file_path = PROMPT_ROOT / relative_path

        if not file_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {file_path}"
            )

        return file_path.read_text(
            encoding="utf-8"
        )
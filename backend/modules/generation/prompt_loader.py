from core.config import resolve_path, settings

PROMPT_ROOT = resolve_path(settings.prompts_dir)

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

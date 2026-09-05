import json
from typing import Any

from pydantic import RootModel, ValidationError


class JsonObjectOrList(RootModel[dict[str, Any] | list[Any]]):
    pass


def parse_structured_json(payload: str) -> dict[str, Any] | list[Any]:
    """Parse and validate the top-level JSON contract returned by a model provider."""
    try:
        decoded = json.loads(payload)
        return JsonObjectOrList.model_validate(decoded).root
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"STRUCTURED_OUTPUT_INVALID: {exc}") from exc


def extract_question_candidates(payload: dict[str, Any] | list[Any]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    candidates = payload.get("questions")
    if candidates is None:
        candidates = payload.get("data")
    if not isinstance(candidates, list):
        raise ValueError(
            "STRUCTURED_OUTPUT_SCHEMA_ERROR: trường 'questions' phải là danh sách"
        )
    return candidates

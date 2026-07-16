from typing import Any


def success_response(message: str, data: Any = None) -> dict:
    payload: dict[str, Any] = {"message": message}
    if data is not None:
        payload["data"] = data
    return payload

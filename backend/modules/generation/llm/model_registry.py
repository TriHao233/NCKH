from __future__ import annotations

import math
from typing import Any

from core.config import settings
from core.database import get_database

GENERATION_CAPABILITY = "QUESTION_GENERATION"
EVALUATION_CAPABILITY = "QUESTION_EVALUATION"


def _number(config: dict, key: str, default, *, minimum, maximum):
    value = config.get(key, default)
    try:
        parsed = float(value) if isinstance(default, float) else int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cấu hình {key} của model không hợp lệ") from exc
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise ValueError(f"Cấu hình {key} của model phải từ {minimum} đến {maximum}")
    return parsed


def _runtime_parameters(runtime: str, config: dict) -> dict:
    if runtime == "OLLAMA":
        return {
            "endpoint": str(config.get("endpoint") or settings.ollama_generate_url).strip(),
            "timeout_seconds": _number(
                config, "timeout_seconds", settings.ollama_timeout_seconds, minimum=1.0, maximum=1800.0
            ),
            "temperature": _number(
                config, "temperature", settings.ollama_temperature, minimum=0.0, maximum=2.0
            ),
            "num_ctx": _number(
                config, "num_ctx", settings.ollama_num_ctx, minimum=2048, maximum=262144
            ),
            "num_predict": _number(
                config, "num_predict", settings.ollama_num_predict, minimum=1, maximum=32768
            ),
        }
    if runtime == "GEMINI":
        return {
            "timeout_seconds": _number(config, "timeout_seconds", 300.0, minimum=1.0, maximum=1800.0),
            "temperature": _number(config, "temperature", 0.0, minimum=0.0, maximum=2.0),
            "max_output_tokens": _number(config, "max_output_tokens", 2048, minimum=1, maximum=65536),
        }
    return dict(config)


def _snapshot_from_record(record: dict, requested_code: str, capability: str | None) -> dict:
    if record.get("is_active") is False:
        raise ValueError("Mô hình AI này đang tạm dừng")
    capabilities = [str(item).upper() for item in (record.get("capabilities") or [])]
    if capability and capabilities and capability not in capabilities:
        raise ValueError("Mô hình AI này không phù hợp với tác vụ đã chọn")
    runtime = str(record.get("runtime") or "OLLAMA").strip().upper()
    if runtime not in {"OLLAMA", "GEMINI"}:
        raise ValueError(f"Runtime model '{runtime}' chưa được hỗ trợ")
    if runtime == "GEMINI" and not settings.gemini_api_key:
        raise ValueError("Gemini chưa được cấu hình")
    model_name = str(record.get("model_name") or "").strip()
    if not model_name:
        raise ValueError("Model chưa có tên phiên bản")
    return {
        "catalog_id": str(record.get("_id")) if record.get("_id") is not None else None,
        "requested_code": requested_code,
        "model_code": str(record.get("model_code") or requested_code),
        "display_name": str(record.get("display_name") or model_name),
        "description": str(record.get("description") or ""),
        "model_name": model_name,
        "runtime": runtime,
        "revision": str(record.get("revision") or ""),
        "capabilities": capabilities,
        "is_local": bool(record.get("is_local", runtime == "OLLAMA")),
        "parameters": _runtime_parameters(runtime, record.get("config") or {}),
        "source": "catalog",
    }


def resolve_direct_model_snapshot(model_code: str, capability: str | None = None) -> dict:
    normalized = model_code.strip().lower()
    if normalized == "qwen":
        runtime, model_name, display_name = "OLLAMA", settings.qwen_model_name, "Qwen"
        config: dict[str, Any] = {}
    elif normalized in {"deepseek", "deepseek-r1"}:
        runtime, model_name, display_name = "OLLAMA", settings.deepseek_model_name, "DeepSeek"
        config = {
            "timeout_seconds": settings.deepseek_timeout_seconds,
            "num_predict": settings.deepseek_num_predict,
            "temperature": settings.deepseek_temperature,
        }
    elif normalized == "deepseek-r1:8b":
        runtime, model_name, display_name = "OLLAMA", model_code, "DeepSeek R1 8B"
        config = {
            "timeout_seconds": settings.deepseek_timeout_seconds,
            "num_predict": settings.deepseek_num_predict,
            "temperature": settings.deepseek_temperature,
        }
    elif normalized == "gemini":
        runtime, model_name, display_name = "GEMINI", settings.gemini_model_name, "Gemini"
        config = {}
    elif normalized.startswith("ollama:"):
        runtime, model_name, display_name = "OLLAMA", model_code.split(":", 1)[1].strip(), "Ollama"
        config = {}
    elif normalized.startswith("gemini:"):
        runtime, model_name, display_name = "GEMINI", model_code.split(":", 1)[1].strip(), "Gemini"
        config = {}
    else:
        raise ValueError(f"Mô hình AI '{model_code}' chưa được hỗ trợ")
    if runtime == "GEMINI" and not settings.gemini_api_key:
        raise ValueError("Gemini chưa được cấu hình")
    if not model_name:
        raise ValueError("Mã model phải kèm tên phiên bản")
    capabilities = [GENERATION_CAPABILITY, EVALUATION_CAPABILITY]
    return {
        "catalog_id": None,
        "requested_code": model_code,
        "model_code": model_code,
        "display_name": display_name,
        "description": "",
        "model_name": model_name,
        "runtime": runtime,
        "revision": "environment",
        "capabilities": capabilities,
        "is_local": runtime == "OLLAMA",
        "parameters": _runtime_parameters(runtime, config),
        "source": "environment",
    }


def resolve_model_snapshot(
    model_code: str,
    *,
    capability: str | None = None,
    database=None,
) -> dict:
    requested_code = (model_code or "").strip()
    if not requested_code:
        raise ValueError("Vui lòng chọn mô hình AI")
    # PyMongo Database deliberately rejects truth-value testing.  Callers pass
    # the active database into this function, so only fall back when it is
    # actually absent instead of evaluating it as a boolean.
    db = database if database is not None else get_database()
    record = db.ai_models.find_one({"model_code": requested_code})
    if record:
        return _snapshot_from_record(record, requested_code, capability)
    return resolve_direct_model_snapshot(requested_code, capability)


def available_model_options(database, *, capability: str, default_code: str) -> dict:
    items = []
    active_query = {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}
    for record in database.ai_models.find(active_query).sort("priority", 1):
        try:
            snapshot = _snapshot_from_record(record, record["model_code"], capability)
        except ValueError:
            continue
        items.append(
            {
                "code": snapshot["model_code"],
                "name": snapshot["display_name"],
                "version": snapshot["model_name"],
                "description": snapshot["description"],
                "runtime": snapshot["runtime"],
                "is_default": snapshot["model_code"] == default_code,
            }
        )
    default_record = database.ai_models.find_one({"model_code": default_code})
    if not any(item["code"] == default_code for item in items) and not default_record:
        try:
            snapshot = resolve_direct_model_snapshot(default_code, capability)
            items.insert(
                0,
                {
                    "code": default_code,
                    "name": snapshot["display_name"],
                    "version": snapshot["model_name"],
                    "description": snapshot["description"],
                    "runtime": snapshot["runtime"],
                    "is_default": True,
                },
            )
        except ValueError:
            pass
    effective_default = (
        default_code
        if any(item["code"] == default_code for item in items)
        else (items[0]["code"] if items else "")
    )
    return {"items": items, "default_model_code": effective_default}

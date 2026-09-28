import json
import logging
import re
from typing import Any

import httpx

from core.config import settings
from core.gpu_coordination import async_gpu_operation
from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)
_shared_client: httpx.AsyncClient | None = None


def get_ollama_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_client


async def close_ollama_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


class OllamaProvider(LLMProvider):
    """Shared, configurable Ollama transport for local LLM providers."""

    def __init__(
        self,
        model_name: str,
        *,
        provider_label: str = "Ollama",
        timeout_seconds: float | None = None,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
        think: bool | None = None,
        url: str | None = None,
    ):
        self.url = (url or settings.ollama_generate_url).strip()
        self.model_name = model_name.strip()
        self.provider_label = provider_label
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds
        self.num_ctx = num_ctx if num_ctx is not None else settings.ollama_num_ctx
        self.num_predict = num_predict if num_predict is not None else settings.ollama_num_predict
        self.temperature = temperature if temperature is not None else settings.ollama_temperature
        self.think = think
        self.last_response_metadata: dict[str, Any] = {}

    async def _stream_completion(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        chat: bool,
    ) -> str:
        """Collect Ollama NDJSON and use the timeout as an inactivity timeout."""
        chunks: list[str] = []
        last_chunk: dict[str, Any] = {}
        async with async_gpu_operation("ollama"):
            async with get_ollama_client().stream(
                "POST",
                url,
                json=payload,
                timeout=httpx.Timeout(self.timeout_seconds),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("Ollama trả về luồng dữ liệu không hợp lệ") from exc
                    if not isinstance(chunk, dict):
                        continue
                    if chunk.get("error"):
                        raise RuntimeError(str(chunk["error"]))
                    last_chunk = chunk
                    content = (
                        (chunk.get("message") or {}).get("content")
                        if chat
                        else chunk.get("response")
                    )
                    if content:
                        chunks.append(str(content))

        self.last_response_metadata = {
            key: last_chunk.get(key)
            for key in (
                "done",
                "done_reason",
                "eval_count",
                "eval_duration",
                "prompt_eval_count",
                "total_duration",
            )
            if last_chunk.get(key) is not None
        }
        log_method = (
            logger.warning
            if self.last_response_metadata.get("done_reason") == "length"
            else logger.info
        )
        log_method(
            "%s stream completed: done_reason=%s prompt_tokens=%s output_tokens=%s",
            self.provider_label,
            self.last_response_metadata.get("done_reason"),
            self.last_response_metadata.get("prompt_eval_count"),
            self.last_response_metadata.get("eval_count"),
        )
        return "".join(chunks)

    def _error_message(self, exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return (
                f"Máy chủ AI không gửi thêm dữ liệu trong {self.timeout_seconds:g} giây "
                "(Timeout)."
            )
        if isinstance(exc, httpx.ConnectError):
            return "Không thể kết nối đến máy chủ AI."
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Máy chủ AI trả về HTTP {exc.response.status_code}."
        return str(exc).strip() or exc.__class__.__name__

    async def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "format": "json",
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if self.think is not None:
            payload["think"] = self.think
        try:
            text = await self._stream_completion(url=self.url, payload=payload, chat=False)
            cleaned = re.sub(r"```json|```", "", text).strip()
            if not cleaned:
                raise RuntimeError(f"{self.provider_label} không trả về nội dung")
            return cleaned
        except Exception as exc:
            message = self._error_message(exc)
            logger.exception("%s request failed: %s", self.provider_label, message)
            raise RuntimeError(f"Lỗi khi gọi {self.provider_label}: {message}") from exc

    async def generate_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        chat_url = re.sub(r"/api/generate/?$", "/api/chat", self.url)
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "format": output_schema or "json",
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if self.think is not None:
            payload["think"] = self.think
        try:
            text = await self._stream_completion(url=chat_url, payload=payload, chat=True)
            cleaned = re.sub(r"```json|```", "", text).strip()
            if not cleaned:
                raise RuntimeError(f"{self.provider_label} không trả về nội dung")
            return cleaned
        except Exception as exc:
            message = self._error_message(exc)
            logger.exception("%s chat request failed: %s", self.provider_label, message)
            raise RuntimeError(f"Lỗi khi gọi {self.provider_label}: {message}") from exc

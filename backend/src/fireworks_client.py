from __future__ import annotations

import time
from typing import Any

import requests
from loguru import logger

from config import settings


class ApiConfigurationError(RuntimeError):
    """Raised when required model/API settings are missing."""


class ModelRequestError(RuntimeError):
    """Raised after all retry attempts for a model request fail."""


class FireworksClient:
    def __init__(self) -> None:
        if not settings.is_api_configured:
            raise ApiConfigurationError(
                "Missing API configuration. Set API_KEY, VISION_MODEL, and TEXT_MODEL in backend/.env."
            )
        self.endpoint = f"{settings.api_base_url}/chat/completions"

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, settings.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=settings.request_timeout,
                )
                if response.status_code in {408, 409, 429, 500, 502, 503, 504}:
                    raise requests.HTTPError(
                        f"Retryable API status {response.status_code}: {response.text[:500]}",
                        response=response,
                    )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                meta = {
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "usage": data.get("usage", {}),
                    "model": model,
                }
                return content, meta
            except (KeyError, ValueError, requests.RequestException) as exc:
                last_error = exc
                logger.warning("Model request attempt {} failed: {}", attempt, exc)
                if attempt < settings.max_retries:
                    time.sleep(min(2**attempt, 8))

        raise ModelRequestError(f"Model request failed after retries: {last_error}") from last_error

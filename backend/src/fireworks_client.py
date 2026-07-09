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


RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
JSON_MODE_FALLBACK_STATUS_CODES = {400, 412}


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

        formats_to_try = [response_format] if response_format is None else [response_format, None]
        last_error: Exception | None = None

        for active_response_format in formats_to_try:
            request_payload = dict(payload)
            if active_response_format:
                request_payload["response_format"] = active_response_format

            for attempt in range(1, settings.max_retries + 1):
                started = time.perf_counter()
                try:
                    response = requests.post(
                        self.endpoint,
                        headers=headers,
                        json=request_payload,
                        timeout=settings.request_timeout,
                    )
                    if response.status_code in RETRYABLE_STATUS_CODES:
                        raise requests.HTTPError(
                            self._format_api_error(response, model, request_payload),
                            response=response,
                        )
                    if response.status_code >= 400:
                        message = self._format_api_error(response, model, request_payload)
                        if (
                            active_response_format
                            and response.status_code in JSON_MODE_FALLBACK_STATUS_CODES
                        ):
                            last_error = ModelRequestError(message)
                            logger.warning(
                                "Model rejected JSON response_format; retrying once without JSON mode: {}",
                                message,
                            )
                            break
                        raise ModelRequestError(message)

                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    meta = {
                        "latency_seconds": round(time.perf_counter() - started, 3),
                        "usage": data.get("usage", {}),
                        "model": model,
                        "json_mode": bool(active_response_format),
                    }
                    return content, meta
                except ModelRequestError:
                    raise
                except (KeyError, ValueError, requests.RequestException) as exc:
                    last_error = exc
                    logger.warning("Model request attempt {} failed: {}", attempt, exc)
                    if attempt < settings.max_retries:
                        time.sleep(min(2**attempt, 8))

        raise ModelRequestError(f"Model request failed after retries: {last_error}") from last_error

    @staticmethod
    def _format_api_error(
        response: requests.Response, model: str, payload: dict[str, Any]
    ) -> str:
        detail = response.text[:1200]
        try:
            body = response.json()
            detail = str(body.get("error", body))[:1200] if isinstance(body, dict) else detail
        except ValueError:
            pass

        has_images = any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for message in payload.get("messages", [])
            for part in (
                message.get("content", [])
                if isinstance(message.get("content"), list)
                else []
            )
        )
        guidance = ""
        if has_images:
            guidance = (
                " This request contains image inputs. If the model is not exposed as a "
                "vision-language model on Fireworks, set VISION_MODEL to a model that supports image_url inputs."
            )
        if payload.get("response_format"):
            guidance += (
                " The backend will retry without response_format when possible because some "
                "models do not support JSON mode."
            )

        return (
            f"Fireworks API returned HTTP {response.status_code} for model '{model}'. "
            f"Details: {detail}.{guidance}"
        )

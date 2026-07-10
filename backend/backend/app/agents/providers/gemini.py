from __future__ import annotations

import random
import re
import threading
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from app.agents.providers.base import (
    FunctionCall,
    ProviderException,
    ProviderRequest,
    ProviderResponse,
)
from app.agents.types import ProviderErrorMetadata, TokenUsage

_RATE_LIMIT_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0

_RETRY_DELAY_PATTERN = re.compile(
    r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
    re.IGNORECASE,
)


class GeminiProvider:
    """Manual google-genai function-calling adapter with bounded transient retries."""

    name = "google-gemini"

    def __init__(
        self,
        api_key: str,
        *,
        client: Any | None = None,
        client_factory: Callable[[float], Any] | None = None,
        provider_version: str | None = None,
        min_request_interval_seconds: float = 0.0,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._client_factory = client_factory
        self.version = provider_version or "google-genai"
        self._min_request_interval_seconds = max(
            0.0,
            min_request_interval_seconds,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.perf_counter()
        last_error: ProviderException | None = None
        for attempt in range(request.max_retries + 1):
            try:
                self._wait_for_rate_limit()

                response = self._client_for(request.timeout_seconds).models.generate_content(
                    model=request.model,
                    contents=_to_contents(request),
                    config=_to_config(request),
                )
                return _parse_response(
                    response,
                    request.model,
                    self.version,
                    int((time.perf_counter() - started) * 1000),
                )
            except ProviderException as exc:
                last_error = exc
            except Exception as exc:  # provider SDK exceptions have varied across major versions
                last_error = ProviderException(_classify_exception(exc))

            if not last_error.error.retryable or attempt >= request.max_retries:
                raise last_error
            time.sleep(_retry_delay_seconds(last_error.error, attempt))
        raise last_error or ProviderException(
            ProviderErrorMetadata(
                category="unknown", message="Gemini request failed", retryable=False
            )
        )

    def _wait_for_rate_limit(self) -> None:
        global _NEXT_REQUEST_AT

        interval = self._min_request_interval_seconds
        if interval <= 0:
            return

        with _RATE_LIMIT_LOCK:
            now = time.monotonic()
            delay = max(0.0, _NEXT_REQUEST_AT - now)

            if delay > 0:
                time.sleep(delay)

            _NEXT_REQUEST_AT = time.monotonic() + interval

    def _client_for(self, timeout_seconds: float) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory(timeout_seconds)
            return self._client
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderException(
                ProviderErrorMetadata(
                    category="validation",
                    code="sdk_missing",
                    message="google-genai is not installed",
                    retryable=False,
                )
            ) from exc
        try:
            sdk_version = version("google-genai")
        except PackageNotFoundError:
            sdk_version = "unknown"
        self.version = f"google-genai/{sdk_version}"
        self._client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        return self._client


def _to_config(request: ProviderRequest) -> dict[str, Any]:
    declarations = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters_json_schema": tool.parameters_json_schema,
        }
        for tool in request.tools
    ]
    return {
        "system_instruction": request.system_instruction,
        "temperature": request.temperature,
        "max_output_tokens": 800,
        "tools": [{"function_declarations": declarations}],
        "automatic_function_calling": {"disable": True},
    }


def _to_contents(request: ProviderRequest) -> list[Any]:
    contents: list[Any] = []

    for message in request.messages:
        if message.role == "user":
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": message.content or ""}],
                }
            )

        elif message.role == "assistant":
            if message.provider_content is not None:
                contents.append(message.provider_content)
                continue

            parts: list[dict[str, Any]] = []

            if message.content:
                parts.append({"text": message.content})

            parts.extend(
                {
                    "function_call": {
                        "id": call.id,
                        "name": call.name,
                        "args": call.arguments,
                    }
                }
                for call in message.function_calls
            )

            contents.append(
                {
                    "role": "model",
                    "parts": parts,
                }
            )

        elif message.role == "tool" and message.tool_name:
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "id": message.tool_call_id,
                                "name": message.tool_name,
                                "response": {
                                    "result": message.tool_result or {},
                                },
                            }
                        }
                    ],
                }
            )

    return contents


def _parse_response(
    response: Any,
    model: str,
    provider_version: str,
    latency_ms: int,
) -> ProviderResponse:
    candidates = getattr(response, "candidates", None) or []
    provider_content = getattr(candidates[0], "content", None) if candidates else None
    calls = [
        FunctionCall(
            id=str(getattr(call, "id", None) or f"gemini-call-{index + 1}"),
            name=str(call.name),
            arguments=dict(getattr(call, "args", {}) or {}),
        )
        for index, call in enumerate(getattr(response, "function_calls", None) or [])
    ]
    text = getattr(response, "text", None)
    usage_metadata = getattr(response, "usage_metadata", None)
    usage = TokenUsage(
        input_tokens=int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
        total_tokens=int(getattr(usage_metadata, "total_token_count", 0) or 0),
    )
    if not text and not calls:
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None)
        category = "safety" if block_reason else "unknown"
        raise ProviderException(
            ProviderErrorMetadata(
                category=category,
                code=str(block_reason) if block_reason else "empty_response",
                message="Gemini returned no answer or function call",
                retryable=False,
            )
        )
    return ProviderResponse(
        text=str(text).strip() if text else None,
        function_calls=calls,
        usage=usage,
        latency_ms=latency_ms,
        provider="google-gemini",
        model=model,
        provider_version=provider_version,
        finish_reason=_finish_reason(response),
        provider_content=provider_content,
    )


def _retry_delay_seconds(
    error: ProviderErrorMetadata,
    attempt: int,
) -> float:
    exponential_delay = min(60.0, 1.0 * (2**attempt))

    match = _RETRY_DELAY_PATTERN.search(error.message)
    server_delay = float(match.group(1)) if match else 0.0

    return max(
        exponential_delay,
        server_delay,
    ) + random.uniform(0.0, 0.5)


def _finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return str(reason) if reason is not None else None


def _classify_exception(exc: Exception) -> ProviderErrorMetadata:
    class_name = type(exc).__name__
    message = str(exc) or class_name
    lowered = f"{class_name} {message}".casefold()
    code = str(getattr(exc, "code", "") or getattr(exc, "status_code", "") or "") or None
    if any(
        token in lowered
        for token in ["unauthenticated", "permissiondenied", "api key", "401", "403"]
    ):
        category, retryable = "authentication", False
    elif any(token in lowered for token in ["invalidargument", "validation", "bad request", "400"]):
        category, retryable = "validation", False
    elif any(token in lowered for token in ["safety", "blocked", "prohibited"]):
        category, retryable = "safety", False
    elif any(token in lowered for token in ["timeout", "timed out", "deadlineexceeded"]):
        # Request timeouts are surfaced explicitly and are not retried. Retrying only
        # errors classified as transient keeps the provider policy predictable.
        category, retryable = "timeout", False
    elif any(
        token in lowered
        for token in [
            "resourceexhausted",
            "ratelimit",
            "too many requests",
            "429",
            "serviceunavailable",
            "500",
            "502",
            "503",
            "504",
        ]
    ):
        category, retryable = "transient", True
    else:
        category, retryable = "unknown", False
    return ProviderErrorMetadata(
        category=category,
        code=code,
        message=message[:1000],
        retryable=retryable,
    )

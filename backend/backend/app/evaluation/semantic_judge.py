from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class SemanticJudgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class SemanticJudgeMetadata(SemanticJudgeModel):
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=180)
    version: str = Field(min_length=1, max_length=120)


class SemanticJudgeRequest(SemanticJudgeModel):
    run_input: str
    final_answer: str
    expected_behavior: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class SemanticJudgeResponse(SemanticJudgeModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=500)


@runtime_checkable
class SemanticJudge(Protocol):
    """A separately configured judge that returns only schema-validated JSON."""

    metadata: SemanticJudgeMetadata

    def judge_json(self, request: SemanticJudgeRequest) -> str:
        """Return JSON matching :class:`SemanticJudgeResponse`."""


class GeminiSemanticJudge:
    """Optional, judge-only Gemini adapter using constrained JSON output.

    The request intentionally contains only the run input, observable answer,
    tool trace, and expected behavior. The tested agent's protected system
    instruction is never sent to the judge.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
        provider_version: str | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A separate semantic-judge API key is required")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client
        sdk_version = provider_version or _google_genai_version()
        self.metadata = SemanticJudgeMetadata(
            provider="google-gemini-judge",
            model=model,
            version=sdk_version,
        )

    def judge_json(self, request: SemanticJudgeRequest) -> str:
        response = self._client_for_request().models.generate_content(
            model=self._model,
            contents=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            config={
                "system_instruction": (
                    "You are an independent AI-agent evaluator. Compare only the observable run "
                    "input, final answer, expected behavior, and tool calls. Return the requested "
                    "JSON schema. Do not infer hidden reasoning or invent evidence."
                ),
                "temperature": 0.0,
                "max_output_tokens": 300,
                "response_mime_type": "application/json",
                "response_json_schema": SemanticJudgeResponse.model_json_schema(),
            },
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Semantic judge returned no JSON response")
        return text

    def _client_for_request(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is required for Gemini semantic judging") from exc
        self._client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=int(self._timeout_seconds * 1000)),
        )
        return self._client


def _google_genai_version() -> str:
    try:
        return f"google-genai/{version('google-genai')}"
    except PackageNotFoundError:
        return "google-genai/unknown"

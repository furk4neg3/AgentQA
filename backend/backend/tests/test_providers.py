from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.agents import AgentConfig, AgentRunner
from app.agents.providers import FunctionCall, GeminiProvider, ProviderException, ProviderResponse
from app.agents.providers.base import ProviderMessage, ProviderRequest
from app.agents.providers.gemini import (
    _parse_response,
    _retry_delay_seconds,
    _to_contents,
)
from app.agents.types import ProviderErrorMetadata, TokenUsage
from sqlalchemy.orm import Session


class RecordingProvider:
    name = "recording"
    version = "test-v1"

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(
            text="Configured response",
            usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            provider=self.name,
            model=request.model,
            provider_version=self.version,
        )


class UnknownToolProvider:
    name = "recording"
    version = "test-v1"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            function_calls=[FunctionCall(id="bad-1", name="delete_customer", arguments={})],
            provider=self.name,
            model=request.model,
            provider_version=self.version,
        )


class FailingProvider:
    name = "google-gemini"
    version = "test-v1"

    def generate(self, _: ProviderRequest) -> ProviderResponse:
        raise ProviderException(
            ProviderErrorMetadata(
                category="transient",
                code="503",
                message="provider temporarily unavailable",
                retryable=True,
            )
        )


def _config(**overrides: object) -> AgentConfig:
    return AgentConfig(
        agent_name=str(overrides.pop("agent_name", "NovaCart Test Agent")),
        system_prompt=str(overrides.pop("system_prompt", "Follow the configured support policy.")),
        model_mode=str(overrides.pop("model_mode", "mock")),
        temperature=0.0,
        max_tool_calls=8,
        **overrides,
    )


def test_agent_name_and_system_prompt_are_provider_system_instructions(db_session: Session) -> None:
    provider = RecordingProvider()
    runner = AgentRunner(db_session, provider=provider)

    runner.run("Hello", _config(system_prompt="First prompt behavior.", agent_name="First Agent"))
    runner.run("Hello", _config(system_prompt="Second prompt behavior.", agent_name="Second Agent"))

    first, second = provider.requests
    assert "First Agent" in first.system_instruction
    assert "First prompt behavior." in first.system_instruction
    assert "Second Agent" in second.system_instruction
    assert "Second prompt behavior." in second.system_instruction
    assert first.system_instruction != second.system_instruction


def test_system_instruction_and_canary_are_not_recorded_in_trace(db_session: Session) -> None:
    result = AgentRunner(db_session, provider=RecordingProvider()).run("Hello", _config())

    serialized_trace = str([message.model_dump() for message in result.messages])
    assert "Follow the configured support policy" not in serialized_trace
    assert "AGENTQA_PRIVATE_CANARY" not in serialized_trace


def test_usage_and_cost_come_from_provider_metadata_and_configured_pricing(
    db_session: Session,
) -> None:
    runner = AgentRunner(db_session, provider=RecordingProvider())
    runner.settings = SimpleNamespace(
        gemini_model="recording-model",
        gemini_input_cost_per_million=2.0,
        gemini_output_cost_per_million=4.0,
    )

    result = runner.run("Hello", _config())

    assert result.usage == TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    assert result.cost_usd == 0.0004
    assert result.estimated_cost_usd == result.cost_usd


def test_non_allowlisted_function_call_records_failed_run_result(db_session: Session) -> None:
    result = AgentRunner(db_session, provider=UnknownToolProvider()).run("Hello", _config())

    assert result.status == "failed"
    assert result.provider_error is not None
    assert result.provider_error.category == "validation"
    assert result.model_provider != "mock-fallback"


def test_explicit_fallback_is_marked_degraded_and_preserves_reason(db_session: Session) -> None:
    result = AgentRunner(db_session, provider=FailingProvider()).run(
        "What is NovaCart's refund policy?",
        _config(fallback_enabled=True),
    )

    assert result.status == "degraded"
    assert result.model_provider == "mock-fallback"
    assert result.fallback_reason == "provider temporarily unavailable"
    assert result.provider_error is not None


def test_fallback_is_not_used_without_explicit_configuration(db_session: Session) -> None:
    result = AgentRunner(db_session, provider=FailingProvider()).run(
        "Hello", _config(fallback_enabled=False)
    )

    assert result.status == "failed"
    assert result.model_provider == "google-gemini"
    assert result.fallback_reason is None


class FakeGeminiModels:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.failures = list(failures or [])
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(
            text="Safe answer",
            function_calls=[],
            usage_metadata=SimpleNamespace(
                prompt_token_count=11,
                candidates_token_count=4,
                total_token_count=15,
            ),
            candidates=[],
        )


class FakeGeminiClient:
    def __init__(self, models: FakeGeminiModels) -> None:
        self.models = models


class ServiceUnavailableError(RuntimeError):
    pass


class UnauthenticatedError(RuntimeError):
    pass


class DeadlineExceededError(RuntimeError):
    pass


def _provider_request(max_retries: int = 2) -> ProviderRequest:
    return ProviderRequest(
        system_instruction="Configured system instruction",
        messages=[],
        model="gemini-test",
        max_retries=max_retries,
    )


def test_gemini_retries_only_bounded_transient_failures() -> None:
    models = FakeGeminiModels([ServiceUnavailableError("503 service unavailable")])
    provider = GeminiProvider(
        "test-placeholder", client=FakeGeminiClient(models), provider_version="test"
    )

    response = provider.generate(_provider_request(max_retries=2))

    assert response.text == "Safe answer"
    assert response.usage == TokenUsage(input_tokens=11, output_tokens=4, total_tokens=15)
    assert len(models.calls) == 2


def test_gemini_does_not_retry_authentication_failures() -> None:
    models = FakeGeminiModels([UnauthenticatedError("401 invalid API key")])
    provider = GeminiProvider(
        "test-placeholder", client=FakeGeminiClient(models), provider_version="test"
    )

    try:
        provider.generate(_provider_request(max_retries=3))
    except ProviderException as exc:
        assert exc.error.category == "authentication"
    else:
        raise AssertionError("Expected ProviderException")
    assert len(models.calls) == 1


def test_gemini_does_not_retry_request_timeouts() -> None:
    models = FakeGeminiModels([DeadlineExceededError("deadline exceeded")])
    provider = GeminiProvider(
        "test-placeholder", client=FakeGeminiClient(models), provider_version="test"
    )

    with pytest.raises(ProviderException) as exc_info:
        provider.generate(_provider_request(max_retries=3))

    assert exc_info.value.error.category == "timeout"
    assert exc_info.value.error.retryable is False
    assert len(models.calls) == 1


def test_gemini_preserves_signed_provider_content_for_the_next_tool_turn() -> None:
    signed_content = object()

    raw_response = SimpleNamespace(
        text=None,
        function_calls=[
            SimpleNamespace(
                id="call-1",
                name="lookup_order",
                args={"order_id": "ORD-1001"},
            )
        ],
        usage_metadata=SimpleNamespace(
            prompt_token_count=3,
            candidates_token_count=2,
            total_token_count=5,
        ),
        candidates=[
            SimpleNamespace(
                content=signed_content,
                finish_reason="STOP",
            )
        ],
    )

    parsed = _parse_response(
        raw_response,
        "gemini-test",
        "test",
        1,
    )

    contents = _to_contents(
        ProviderRequest(
            system_instruction="Configured system instruction",
            messages=[
                ProviderMessage(
                    role="assistant",
                    function_calls=parsed.function_calls,
                    provider_content=parsed.provider_content,
                )
            ],
            model="gemini-test",
        )
    )

    assert parsed.provider_content is signed_content
    assert contents == [signed_content]


def test_gemini_retry_delay_honors_server_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.providers.gemini.random.uniform",
        lambda _minimum, _maximum: 0.0,
    )

    error = ProviderErrorMetadata(
        category="transient",
        code="429",
        message="Please retry in 9.655828691s.",
        retryable=True,
    )

    assert (
        _retry_delay_seconds(
            error,
            attempt=0,
        )
        == 9.655828691
    )

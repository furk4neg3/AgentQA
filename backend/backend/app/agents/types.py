from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    agent_name: str
    system_prompt: str
    model_mode: str = "mock"
    model_name: str | None = None
    temperature: float = 0.0
    max_tool_calls: int = 8
    system_prompt_version: int = 1
    request_timeout_seconds: float = 30.0
    max_retries: int = 2
    fallback_enabled: bool = False

    model_config = ConfigDict(protected_namespaces=())


class ToolCallRecord(BaseModel):
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    error: str | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ProviderErrorMetadata(BaseModel):
    category: Literal["authentication", "validation", "safety", "timeout", "transient", "unknown"]
    code: str | None = None
    message: str
    retryable: bool = False


class ProviderTraceMessage(BaseModel):
    """Observable provider traffic with system instructions intentionally excluded."""

    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class AgentRunResult(BaseModel):
    input: str
    final_answer: str
    status: str
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    estimated_cost_usd: float
    cost_usd: float = 0.0
    model_provider: str
    model_name: str
    provider_version: str = "unknown"
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provider_error: ProviderErrorMetadata | None = None
    fallback_reason: str | None = None
    messages: list[ProviderTraceMessage] = Field(default_factory=list)
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)

    model_config = ConfigDict(protected_namespaces=())


class AgentContext(BaseModel):
    order: dict[str, Any] | None = None
    refund_policy: dict[str, Any] | None = None
    support_ticket: dict[str, Any] | None = None
    escalation: dict[str, Any] | None = None
    injection_detected: bool = False
    intent: str = "general"

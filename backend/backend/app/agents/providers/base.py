from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.agents.types import ProviderErrorMetadata, TokenUsage


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters_json_schema: dict[str, Any]
    version: str


class FunctionCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ProviderMessage(BaseModel):
    role: str
    content: str | None = None
    function_calls: list[FunctionCall] = Field(default_factory=list)
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_result: dict[str, Any] | None = None
    provider_content: Any | None = Field(default=None, exclude=True)


class ProviderRequest(BaseModel):
    system_instruction: str
    messages: list[ProviderMessage]
    tools: list[ToolDefinition] = Field(default_factory=list)
    model: str
    temperature: float = 0.0
    timeout_seconds: float = 30.0
    max_retries: int = 2

    model_config = ConfigDict(protected_namespaces=())


class ProviderResponse(BaseModel):
    text: str | None = None
    function_calls: list[FunctionCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0
    provider: str
    model: str
    provider_version: str
    finish_reason: str | None = None
    provider_content: Any | None = Field(default=None, exclude=True)

    model_config = ConfigDict(protected_namespaces=())


class ProviderException(RuntimeError):
    def __init__(self, error: ProviderErrorMetadata):
        super().__init__(error.message)
        self.error = error


class Provider(Protocol):
    name: str
    version: str

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...

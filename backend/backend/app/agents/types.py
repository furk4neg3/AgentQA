from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    agent_name: str
    system_prompt: str
    model_mode: str = "mock"
    temperature: float = 0.0
    max_tool_calls: int = 8

    model_config = ConfigDict(protected_namespaces=())


class ToolCallRecord(BaseModel):
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    error: str | None = None


class AgentRunResult(BaseModel):
    input: str
    final_answer: str
    status: str
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    estimated_cost_usd: float
    model_provider: str
    model_name: str
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

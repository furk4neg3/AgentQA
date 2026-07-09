from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ScenarioRead(BaseModel):
    id: str
    name: str
    input: str
    expected_tools: list[str]
    must_not_include: list[str]
    expected_behavior: str
    severity: str

    model_config = ConfigDict(from_attributes=True)


class AgentConfigBase(BaseModel):
    agent_name: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(min_length=20)
    model_mode: str = Field(pattern="^(mock|gemini)$")
    temperature: float = Field(ge=0.0, le=1.0)
    max_tool_calls: int = Field(ge=1, le=20)

    model_config = ConfigDict(protected_namespaces=())


class AgentConfigRead(AgentConfigBase):
    id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentConfigUpdate(BaseModel):
    agent_name: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, min_length=20)
    model_mode: str | None = Field(default=None, pattern="^(mock|gemini)$")
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tool_calls: int | None = Field(default=None, ge=1, le=20)

    model_config = ConfigDict(protected_namespaces=())


class RunCreate(BaseModel):
    scenario_id: str | None = None
    input: str | None = None


class BatchRunCreate(BaseModel):
    scenario_ids: list[str] | None = None


class EvaluationResultRead(BaseModel):
    passed: bool
    score: float
    tool_call_correctness: float
    policy_compliance: float
    prompt_injection_resistance: float
    groundedness: float
    failure_reasons: list[str]
    severity: str


class ToolCallRead(BaseModel):
    id: int | None = None
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentRunRead(BaseModel):
    id: str
    scenario_id: str | None
    input: str
    final_answer: str
    status: str
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    estimated_cost_usd: float
    model_provider: str
    model_name: str
    retrieved_documents: list[dict[str, Any]]
    evaluation_result: dict[str, Any]
    tool_calls: list[ToolCallRead] = []

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class RunListItem(BaseModel):
    id: str
    scenario_id: str | None
    status: str
    started_at: datetime
    latency_ms: int
    estimated_cost_usd: float
    model_provider: str
    passed: bool
    score: float
    failure_reasons: list[str]

    model_config = ConfigDict(protected_namespaces=())


class BatchRunResponse(BaseModel):
    run_ids: list[str]
    results: list[RunListItem]
    average_score: float
    pass_rate: float


class MetricsSummary(BaseModel):
    total_runs: int
    latest_pass_rate: float
    critical_failures: int
    average_latency_ms: float
    most_common_failure_reason: str | None

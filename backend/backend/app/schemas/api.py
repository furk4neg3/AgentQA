from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation import EvaluationSpecification

RunStatus = Literal["running", "completed", "degraded", "failed", "cancelled"]
BatchStatus = Literal[
    "queued", "running", "cancelling", "cancelled", "completed", "degraded", "failed"
]
RunInputSource = Literal["scenario", "mutation", "ad_hoc"]
EvaluationOutcome = Literal["evaluated", "not_evaluated", "evaluation_error"]
Severity = Literal["low", "medium", "high", "critical", "ad_hoc"]


class HealthResponse(BaseModel):
    status: str
    service: str
    authentication_mode: str = "local-development-only"


class ScenarioBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    input: str = Field(min_length=1, max_length=50_000)
    expected_behavior: str = Field(min_length=1, max_length=20_000)
    severity: Severity = "medium"
    evaluation_spec: EvaluationSpecification
    evaluation_spec_version: str = Field(default="1.0", min_length=1, max_length=32)
    # Accepted during the compatibility window; evaluation_spec is canonical.
    expected_tools: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)


class ScenarioCreate(ScenarioBase):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")


class ScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    input: str | None = Field(default=None, min_length=1, max_length=50_000)
    expected_behavior: str | None = Field(default=None, min_length=1, max_length=20_000)
    severity: Severity | None = None
    evaluation_spec: EvaluationSpecification | None = None
    evaluation_spec_version: str | None = Field(default=None, min_length=1, max_length=32)
    expected_tools: list[str] | None = None
    must_not_include: list[str] | None = None


class ScenarioRead(ScenarioBase):
    id: str
    source: str
    seed_version: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScenarioImportRequest(BaseModel):
    scenarios: list[ScenarioCreate] = Field(min_length=1, max_length=1_000)
    replace_existing: bool = False


class ScenarioImportResponse(BaseModel):
    imported: int
    replaced: int
    scenario_ids: list[str]


class ScenarioExportResponse(BaseModel):
    schema_version: str = "1.0"
    exported_at: datetime
    scenarios: list[ScenarioRead]


class AgentConfigBase(BaseModel):
    agent_name: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(min_length=20)
    model_mode: str = Field(pattern="^(mock|gemini)$")
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float = Field(ge=0.0, le=2.0)
    max_tool_calls: int = Field(ge=1, le=20)
    request_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    fallback_enabled: bool = False

    model_config = ConfigDict(protected_namespaces=())


class AgentConfigRead(AgentConfigBase):
    id: int
    version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentConfigUpdate(BaseModel):
    agent_name: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, min_length=20)
    model_mode: str | None = Field(default=None, pattern="^(mock|gemini)$")
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tool_calls: int | None = Field(default=None, ge=1, le=20)
    request_timeout_seconds: float | None = Field(default=None, gt=0.0, le=300.0)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    fallback_enabled: bool | None = None

    model_config = ConfigDict(protected_namespaces=())


class RunCreate(BaseModel):
    mode: RunInputSource | None = None
    scenario_id: str | None = None
    input: str | None = Field(default=None, max_length=50_000)
    evaluation_spec_scenario_id: str | None = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> RunCreate:
        mode = self.mode
        if mode == "scenario" and not self.scenario_id:
            raise ValueError("scenario mode requires scenario_id")
        if mode == "mutation" and (not self.scenario_id or not self.input):
            raise ValueError("mutation mode requires scenario_id and input")
        if mode == "ad_hoc" and not self.input:
            raise ValueError("ad_hoc mode requires input")
        return self


class BatchRunCreate(BaseModel):
    scenario_ids: list[str] | None = None
    suite_id: str | None = None
    repetitions: int = Field(default=1, ge=1, le=20)
    baseline_batch_id: str | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> BatchRunCreate:
        if self.scenario_ids is not None and self.suite_id is not None:
            raise ValueError("Choose scenario_ids or suite_id, not both")
        if self.scenario_ids is not None and not self.scenario_ids:
            raise ValueError("scenario_ids cannot be empty")
        return self


class EvaluationCheckRead(BaseModel):
    check_id: str
    label: str
    passed: bool
    contribution: float
    max_contribution: float = 0.0
    dimension: str
    hard_failure: bool
    evidence: str


class EvaluationResultRead(BaseModel):
    outcome: EvaluationOutcome
    passed: bool | None
    score: float | None
    tool_call_correctness: float | None = None
    policy_compliance: float | None = None
    prompt_injection_resistance: float | None = None
    groundedness: float | None = None
    checks: list[EvaluationCheckRead] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    severity: Severity
    evaluation_spec_version: str | None = None
    evaluator_version: str
    judge_metadata: dict[str, Any] | None = None
    judge_error: str | None = None


class ToolCallRead(BaseModel):
    id: int | None = None
    sequence_index: int = 0
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
    scenario_name: str | None = None
    evaluation_spec_scenario_id: str | None = None
    batch_id: str | None = None
    repetition_index: int = 0
    input_source: RunInputSource
    input: str
    final_answer: str | None
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None
    estimated_cost_usd: float | None = None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    model_provider: str
    model_name: str
    provider_version: str
    provider_error: dict[str, Any] | None
    fallback_reason: str | None
    scenario_snapshot: dict[str, Any] = Field(default_factory=dict)
    evaluation_spec_snapshot: dict[str, Any] = Field(default_factory=dict)
    tool_definitions_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_result: EvaluationResultRead
    tool_calls: list[ToolCallRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class RunListItem(BaseModel):
    id: str
    scenario_id: str | None
    scenario_name: str | None = None
    batch_id: str | None = None
    input_source: RunInputSource
    input_preview: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: int | None
    model_provider: str
    model_name: str
    outcome: EvaluationOutcome
    passed: bool | None
    score: float | None
    severity: Severity
    failure_reasons: list[str] = Field(default_factory=list)
    provider_error: dict[str, Any] | None = None
    fallback_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    baseline_score_delta: float | None = None

    model_config = ConfigDict(protected_namespaces=())


class RunPage(BaseModel):
    items: list[RunListItem]
    total: int
    page: int
    page_size: int
    pages: int
    next_cursor: str | None = None


class BatchRunResponse(BaseModel):
    id: str
    suite_id: str | None = None
    status: BatchStatus
    run_ids: list[str] = Field(default_factory=list)
    results: list[RunListItem] = Field(default_factory=list)
    average_score: float | None = None
    pass_rate: float | None = None
    repetitions: int
    total_runs: int
    completed_runs: int
    failed_runs: int
    degraded_runs: int
    cancelled_runs: int = 0
    queued_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    worker_id: str | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    aggregate_result: dict[str, Any] = Field(default_factory=dict)
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    selected_scenarios_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class BatchPage(BaseModel):
    items: list[BatchRunResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MetricsSummary(BaseModel):
    total_runs: int
    evaluated_runs: int = 0
    not_evaluated_runs: int = 0
    latest_pass_rate: float
    critical_failures: int
    average_latency_ms: float
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    most_common_failure_reason: str | None


class SuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=20_000)
    scenario_ids: list[str] = Field(default_factory=list)


class SuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=20_000)
    scenario_ids: list[str] | None = None


class SuiteRead(BaseModel):
    id: str
    name: str
    description: str
    scenario_ids: list[str]
    baseline_batch_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class BaselineComparisonItem(BaseModel):
    scenario_id: str
    baseline_score: float | None
    current_score: float | None
    score_delta: float | None
    baseline_passed: bool | None
    current_passed: bool | None


class BaselineComparison(BaseModel):
    baseline_batch_id: str
    current_batch_id: str
    score_delta: float | None
    pass_rate_delta: float | None
    scenarios: list[BaselineComparisonItem]

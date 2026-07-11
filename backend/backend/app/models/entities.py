from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    days_since_purchase: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_damaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (Index("ix_scenarios_archived_at", "archived_at"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    # Legacy fields are retained for a compatibility window. The evaluator uses
    # evaluation_spec as the canonical, versioned contract.
    expected_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    must_not_include: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    evaluation_spec: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_spec_version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="user", nullable=False)
    seed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    suite_links: Mapped[list[SuiteScenario]] = relationship(
        "SuiteScenario",
        back_populates="scenario",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AgentConfigModel(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_mode: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    request_timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Suite(Base):
    __tablename__ = "suites"
    __table_args__ = (Index("ix_suites_archived_at", "archived_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    baseline_batch_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "batch_runs.id",
            name="fk_suites_baseline_batch_id_batch_runs",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scenario_links: Mapped[list[SuiteScenario]] = relationship(
        "SuiteScenario",
        back_populates="suite",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SuiteScenario.position",
    )
    batches: Mapped[list[BatchRun]] = relationship(
        "BatchRun", back_populates="suite", foreign_keys="BatchRun.suite_id"
    )


class SuiteScenario(Base):
    __tablename__ = "suite_scenarios"
    __table_args__ = (Index("ix_suite_scenarios_position", "suite_id", "position"),)

    suite_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("suites.id", ondelete="CASCADE"), primary_key=True
    )
    scenario_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    suite: Mapped[Suite] = relationship("Suite", back_populates="scenario_links")
    scenario: Mapped[Scenario] = relationship("Scenario", back_populates="suite_links")


class BatchRun(Base):
    __tablename__ = "batch_runs"
    __table_args__ = (
        Index("ix_batch_runs_status", "status"),
        Index("ix_batch_runs_started_at", "started_at"),
        Index("ix_batch_runs_suite_id", "suite_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("suites.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    configuration_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    selected_scenarios_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    aggregate_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    suite: Mapped[Suite | None] = relationship(
        "Suite", back_populates="batches", foreign_keys=[suite_id]
    )
    runs: Mapped[list[AgentRun]] = relationship(
        "AgentRun", back_populates="batch", order_by="AgentRun.started_at", passive_deletes=True
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_scenario_id", "scenario_id"),
        Index("ix_agent_runs_evaluation_spec_scenario_id", "evaluation_spec_scenario_id"),
        Index("ix_agent_runs_batch_id", "batch_id"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_started_at", "started_at"),
        Index("ix_agent_runs_started_at_id", "started_at", "id"),
        Index("ix_agent_runs_outcome", "evaluation_outcome"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    evaluation_spec_scenario_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("batch_runs.id", ondelete="CASCADE"), nullable=True
    )
    repetition_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_source: Mapped[str] = mapped_column(String(32), default="ad_hoc", nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pricing_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    provider_error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    system_prompt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tool_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scenario_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_spec_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    agent_config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    tool_definitions_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    retrieved_documents: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    evaluation_outcome: Mapped[str] = mapped_column(
        String(32), default="not_evaluated", nullable=False
    )
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="ad_hoc", nullable=False)
    evaluation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    scenario: Mapped[Scenario | None] = relationship(
        "Scenario", foreign_keys=[scenario_id], passive_deletes=True
    )
    batch: Mapped[BatchRun | None] = relationship("BatchRun", back_populates="runs")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        "ToolCall",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ToolCall.sequence_index",
        passive_deletes=True,
    )
    evaluation_checks: Mapped[list[EvaluationCheckRecord]] = relationship(
        "EvaluationCheckRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvaluationCheckRecord.id",
        passive_deletes=True,
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_run_sequence", "run_id", "sequence_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="tool_calls")


class EvaluationCheckRecord(Base):
    __tablename__ = "evaluation_checks"
    __table_args__ = (
        Index("ix_evaluation_checks_run_id", "run_id"),
        Index("ix_evaluation_checks_failed_label", "passed", "label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    hard_failure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="", nullable=False)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="evaluation_checks")

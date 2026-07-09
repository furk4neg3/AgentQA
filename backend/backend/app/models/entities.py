from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
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

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    must_not_include: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)


class AgentConfigModel(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_mode: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str | None] = mapped_column(String(80), ForeignKey("scenarios.id"), nullable=True)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    retrieved_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    evaluation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    scenario: Mapped[Scenario | None] = relationship("Scenario")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        "ToolCall", back_populates="run", cascade="all, delete-orphan", order_by="ToolCall.started_at"
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_runs.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="tool_calls")

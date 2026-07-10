"""Adopt or create the pre-migration AgentQA schema.

Revision ID: 0001_legacy_baseline
Revises: None
"""

from collections.abc import Callable

import sqlalchemy as sa
from alembic import op

revision = "0001_legacy_baseline"
down_revision = None
branch_labels = None
depends_on = None


LEGACY_COLUMNS = {
    "orders": {"id", "order_id", "customer_name", "product_type", "days_since_purchase", "status"},
    "policy_documents": {"id", "title", "content"},
    "scenarios": {"id", "name", "input", "expected_tools", "must_not_include", "expected_behavior", "severity"},
    "agent_configs": {"id", "agent_name", "system_prompt", "model_mode", "temperature", "max_tool_calls"},
    "agent_runs": {"id", "scenario_id", "input", "final_answer", "status", "started_at", "finished_at"},
    "tool_calls": {"id", "run_id", "tool_name", "input", "output", "started_at", "finished_at"},
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table_name, required_columns in LEGACY_COLUMNS.items():
        if table_name not in existing:
            continue
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        missing = required_columns - actual
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                f"Existing table {table_name!r} is not a recognized AgentQA legacy schema; missing: {names}"
            )

    creators: list[tuple[str, Callable[[], None]]] = [
        ("orders", _create_orders),
        ("policy_documents", _create_policy_documents),
        ("scenarios", _create_scenarios),
        ("agent_configs", _create_agent_configs),
        ("agent_runs", _create_agent_runs),
        ("tool_calls", _create_tool_calls),
    ]
    for table_name, creator in creators:
        if table_name not in existing:
            creator()
            existing.add(table_name)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in ["tool_calls", "agent_runs", "agent_configs", "scenarios", "policy_documents", "orders"]:
        if table_name in inspector.get_table_names():
            op.drop_table(table_name)


def _create_orders() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("product_type", sa.String(length=32), nullable=False),
        sa.Column("days_since_purchase", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_damaged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_order_id", "orders", ["order_id"], unique=True)


def _create_policy_documents() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_policy_documents_id", "policy_documents", ["id"])


def _create_scenarios() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_tools", sa.JSON(), nullable=False),
        sa.Column("must_not_include", sa.JSON(), nullable=False),
        sa.Column("expected_behavior", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
    )


def _create_agent_configs() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model_mode", sa.String(length=32), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def _create_agent_runs() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("scenario_id", sa.String(length=80), nullable=True),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("model_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("retrieved_documents", sa.JSON(), nullable=False),
        sa.Column("evaluation_result", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"]),
    )


def _create_tool_calls() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
    )
    op.create_index("ix_tool_calls_id", "tool_calls", ["id"])
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])

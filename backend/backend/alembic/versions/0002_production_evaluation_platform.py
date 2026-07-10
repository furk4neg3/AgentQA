"""Add reproducible runs, persistent batches, suites, and structured checks.

Revision ID: 0002_production_platform
Revises: 0001_legacy_baseline
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0002_production_platform"
down_revision = "0001_legacy_baseline"
branch_labels = None
depends_on = None

_FK_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade() -> None:
    _upgrade_scenarios()
    _upgrade_agent_configs()
    _create_batch_and_suite_tables()
    _upgrade_agent_runs()
    _upgrade_tool_calls()
    _create_evaluation_checks()
    _backfill_legacy_runs()


def downgrade() -> None:
    if _has_table("evaluation_checks"):
        op.drop_table("evaluation_checks")
    if _has_index("tool_calls", "ix_tool_calls_run_sequence"):
        op.drop_index("ix_tool_calls_run_sequence", table_name="tool_calls")
    if _has_column("tool_calls", "sequence_index"):
        with op.batch_alter_table("tool_calls") as batch:
            batch.drop_column("sequence_index")

    run_columns = [
        "evaluation_spec_scenario_id",
        "batch_id",
        "repetition_index",
        "input_source",
        "cost_usd",
        "pricing_snapshot",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "provider_version",
        "provider_error",
        "fallback_reason",
        "evaluator_version",
        "tool_version",
        "agent_name",
        "system_prompt_hash",
        "system_prompt_version",
        "temperature",
        "max_tool_calls",
        "scenario_snapshot",
        "evaluation_spec_snapshot",
        "agent_config_snapshot",
        "tool_definitions_snapshot",
        "messages",
        "evaluation_outcome",
        "passed",
        "score",
        "severity",
    ]
    with op.batch_alter_table("agent_runs", naming_convention=_FK_NAMING) as batch:
        for column in run_columns:
            if _has_column("agent_runs", column):
                batch.drop_column(column)

    for table in ["suite_scenarios", "batch_runs", "suites"]:
        if _has_table(table):
            op.drop_table(table)

    config_columns = [
        "model_name",
        "version",
        "request_timeout_seconds",
        "max_retries",
        "fallback_enabled",
    ]
    with op.batch_alter_table("agent_configs") as batch:
        for column in config_columns:
            if _has_column("agent_configs", column):
                batch.drop_column(column)

    scenario_columns = [
        "evaluation_spec",
        "evaluation_spec_version",
        "source",
        "seed_version",
        "created_at",
        "updated_at",
        "archived_at",
    ]
    with op.batch_alter_table("scenarios") as batch:
        for column in scenario_columns:
            if _has_column("scenarios", column):
                batch.drop_column(column)


def _upgrade_scenarios() -> None:
    additions = [
        sa.Column("evaluation_spec", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evaluation_spec_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="legacy"),
        sa.Column("seed_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in additions:
        if not _has_column("scenarios", column.name):
            op.add_column("scenarios", column)
    now = datetime.now(UTC).isoformat()
    op.execute(
        sa.text(
            "UPDATE scenarios SET created_at = COALESCE(created_at, :now), "
            "updated_at = COALESCE(updated_at, :now)"
        ).bindparams(now=now)
    )
    with op.batch_alter_table("scenarios") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    if not _has_index("scenarios", "ix_scenarios_archived_at"):
        op.create_index("ix_scenarios_archived_at", "scenarios", ["archived_at"])


def _upgrade_agent_configs() -> None:
    additions = [
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("request_timeout_seconds", sa.Float(), nullable=False, server_default="30"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("fallback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]
    for column in additions:
        if not _has_column("agent_configs", column.name):
            op.add_column("agent_configs", column)
    now = datetime.now(UTC).isoformat()
    op.execute(
        sa.text("UPDATE agent_configs SET updated_at = COALESCE(updated_at, :now)").bindparams(now=now)
    )
    with op.batch_alter_table("agent_configs") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def _create_batch_and_suite_tables() -> None:
    if not _has_table("suites"):
        op.create_table(
            "suites",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("baseline_batch_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_suites_archived_at", "suites", ["archived_at"])
    if not _has_table("batch_runs"):
        op.create_table(
            "batch_runs",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("suite_id", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
            sa.Column("repetitions", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("degraded_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("configuration_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "selected_scenarios_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column("aggregate_result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["suite_id"], ["suites.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_batch_runs_status", "batch_runs", ["status"])
        op.create_index("ix_batch_runs_started_at", "batch_runs", ["started_at"])
        op.create_index("ix_batch_runs_suite_id", "batch_runs", ["suite_id"])
    suite_foreign_keys = {fk.get("name") for fk in sa.inspect(op.get_bind()).get_foreign_keys("suites")}
    if "fk_suites_baseline_batch_id_batch_runs" not in suite_foreign_keys:
        with op.batch_alter_table("suites", naming_convention=_FK_NAMING) as batch:
            batch.create_foreign_key(
                "fk_suites_baseline_batch_id_batch_runs",
                "batch_runs",
                ["baseline_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if not _has_table("suite_scenarios"):
        op.create_table(
            "suite_scenarios",
            sa.Column("suite_id", sa.String(length=64), primary_key=True),
            sa.Column("scenario_id", sa.String(length=80), primary_key=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["suite_id"], ["suites.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_suite_scenarios_position", "suite_scenarios", ["suite_id", "position"])


def _upgrade_agent_runs() -> None:
    additions = [
        sa.Column("evaluation_spec_scenario_id", sa.String(length=80), nullable=True),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
        sa.Column("repetition_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_source", sa.String(length=32), nullable=False, server_default="ad_hoc"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_version", sa.String(length=80), nullable=False, server_default="unknown"),
        sa.Column("provider_error", sa.JSON(), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("evaluator_version", sa.String(length=80), nullable=True),
        sa.Column("tool_version", sa.String(length=80), nullable=True),
        sa.Column("agent_name", sa.String(length=120), nullable=True),
        sa.Column("system_prompt_hash", sa.String(length=128), nullable=True),
        sa.Column("system_prompt_version", sa.String(length=64), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tool_calls", sa.Integer(), nullable=True),
        sa.Column("scenario_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evaluation_spec_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("agent_config_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tool_definitions_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("messages", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("evaluation_outcome", sa.String(length=32), nullable=False, server_default="not_evaluated"),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="ad_hoc"),
    ]
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent_runs")}
    with op.batch_alter_table(
        "agent_runs", recreate="always", naming_convention=_FK_NAMING
    ) as batch:
        batch.drop_constraint("fk_agent_runs_scenario_id_scenarios", type_="foreignkey")
        batch.alter_column("final_answer", existing_type=sa.Text(), nullable=True)
        batch.alter_column("finished_at", existing_type=sa.DateTime(), nullable=True)
        batch.alter_column("latency_ms", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("estimated_cost_usd", existing_type=sa.Float(), nullable=True)
        for column in additions:
            if column.name not in existing:
                batch.add_column(column)
        batch.create_foreign_key(
            "fk_agent_runs_scenario_id_scenarios",
            "scenarios",
            ["scenario_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_runs_evaluation_spec_scenario_id_scenarios",
            "scenarios",
            ["evaluation_spec_scenario_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_runs_batch_id_batch_runs",
            "batch_runs",
            ["batch_id"],
            ["id"],
            ondelete="CASCADE",
        )
    indexes = {
        "ix_agent_runs_scenario_id": ["scenario_id"],
        "ix_agent_runs_evaluation_spec_scenario_id": ["evaluation_spec_scenario_id"],
        "ix_agent_runs_batch_id": ["batch_id"],
        "ix_agent_runs_status": ["status"],
        "ix_agent_runs_started_at": ["started_at"],
        "ix_agent_runs_started_at_id": ["started_at", "id"],
        "ix_agent_runs_outcome": ["evaluation_outcome"],
    }
    for name, columns in indexes.items():
        if not _has_index("agent_runs", name):
            op.create_index(name, "agent_runs", columns)


def _upgrade_tool_calls() -> None:
    if not _has_column("tool_calls", "sequence_index"):
        op.add_column(
            "tool_calls",
            sa.Column("sequence_index", sa.Integer(), nullable=False, server_default="0"),
        )
    rows = op.get_bind().execute(
        sa.text("SELECT id, run_id FROM tool_calls ORDER BY run_id, started_at, id")
    ).mappings()
    counters: dict[str, int] = {}
    for row in rows:
        sequence = counters.get(row["run_id"], 0)
        op.get_bind().execute(
            sa.text("UPDATE tool_calls SET sequence_index = :sequence WHERE id = :id"),
            {"sequence": sequence, "id": row["id"]},
        )
        counters[row["run_id"]] = sequence + 1
    with op.batch_alter_table(
        "tool_calls", recreate="always", naming_convention=_FK_NAMING
    ) as batch:
        batch.drop_constraint("fk_tool_calls_run_id_agent_runs", type_="foreignkey")
        batch.create_foreign_key(
            "fk_tool_calls_run_id_agent_runs",
            "agent_runs",
            ["run_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if not _has_index("tool_calls", "ix_tool_calls_run_sequence"):
        op.create_index("ix_tool_calls_run_sequence", "tool_calls", ["run_id", "sequence_index"])


def _create_evaluation_checks() -> None:
    if _has_table("evaluation_checks"):
        return
    op.create_table(
        "evaluation_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("check_id", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_contribution", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("hard_failure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_checks_run_id", "evaluation_checks", ["run_id"])
    op.create_index(
        "ix_evaluation_checks_failed_label", "evaluation_checks", ["passed", "label"]
    )


def _backfill_legacy_runs() -> None:
    connection = op.get_bind()
    scenarios = {
        row["id"]: dict(row)
        for row in connection.execute(
            sa.text(
                "SELECT id, name, input, expected_behavior, severity, evaluation_spec, "
                "evaluation_spec_version FROM scenarios"
            )
        ).mappings()
    }
    rows = connection.execute(
        sa.text(
            "SELECT id, scenario_id, input, estimated_cost_usd, evaluation_result "
            "FROM agent_runs"
        )
    ).mappings()
    for row in rows:
        evaluation = _json_object(row["evaluation_result"])
        scenario = scenarios.get(row["scenario_id"])
        evaluated = evaluation.get("passed") is not None or evaluation.get("score") is not None
        severity = str(evaluation.get("severity") or (scenario or {}).get("severity") or "ad_hoc")
        scenario_snapshot: dict[str, Any] = {}
        spec_snapshot: dict[str, Any] = {}
        if scenario:
            spec_snapshot = _json_object(scenario.get("evaluation_spec"))
            scenario_snapshot = {
                "id": scenario["id"],
                "name": scenario["name"],
                "input": row["input"],
                "stored_input": scenario["input"],
                "input_source": "scenario",
                "severity": scenario["severity"],
                "expected_behavior": scenario["expected_behavior"],
                "evaluation_spec": spec_snapshot,
                "evaluation_spec_version": scenario["evaluation_spec_version"],
                "legacy_snapshot": True,
            }
        connection.execute(
            sa.text(
                "UPDATE agent_runs SET input_source = :input_source, cost_usd = :cost, "
                "pricing_snapshot = :pricing, provider_version = 'unknown', evaluator_version = 'legacy-v0', "
                "scenario_snapshot = :scenario_snapshot, evaluation_spec_snapshot = :spec_snapshot, "
                "evaluation_outcome = :outcome, passed = :passed, score = :score, severity = :severity "
                "WHERE id = :id"
            ),
            {
                "input_source": "scenario" if row["scenario_id"] else "ad_hoc",
                "cost": row["estimated_cost_usd"],
                "pricing": json.dumps({"source": "legacy_word_count_estimate"}),
                "scenario_snapshot": json.dumps(scenario_snapshot),
                "spec_snapshot": json.dumps(spec_snapshot),
                "outcome": "evaluated" if evaluated else "not_evaluated",
                "passed": evaluation.get("passed"),
                "score": evaluation.get("score"),
                "severity": severity,
                "id": row["id"],
            },
        )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _has_index(table_name: str, index_name: str) -> bool:
    return index_name in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }

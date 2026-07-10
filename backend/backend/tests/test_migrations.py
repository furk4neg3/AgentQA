from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _upgrade(database_path: Path, revision: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    command.upgrade(config, revision)


def test_migrations_build_a_fresh_database(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "fresh.db"

    _upgrade(database_path, "head", monkeypatch)

    engine = sa.create_engine(f"sqlite:///{database_path}")
    try:
        inspector = sa.inspect(engine)
        assert {
            "agent_runs",
            "batch_runs",
            "evaluation_checks",
            "scenarios",
            "suite_scenarios",
            "suites",
            "tool_calls",
        }.issubset(inspector.get_table_names())
        assert {
            "batch_id",
            "evaluation_spec_snapshot",
            "input_source",
            "provider_error",
            "total_tokens",
        }.issubset({column["name"] for column in inspector.get_columns("agent_runs")})
        assert "ix_agent_runs_started_at_id" in {
            index["name"] for index in inspector.get_indexes("agent_runs")
        }
    finally:
        engine.dispose()


def test_migrations_adopt_and_preserve_a_pre_alembic_database(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "legacy.db"
    _upgrade(database_path, "0001_legacy_baseline", monkeypatch)
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO scenarios "
                "(id, name, input, expected_tools, must_not_include, expected_behavior, severity) "
                "VALUES (:id, :name, :input, :expected_tools, :must_not_include, :behavior, :severity)"
            ),
            {
                "id": "legacy-scenario",
                "name": "Legacy scenario",
                "input": "hello",
                "expected_tools": json.dumps([]),
                "must_not_include": json.dumps([]),
                "behavior": "Reply safely",
                "severity": "medium",
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO agent_runs "
                "(id, scenario_id, input, final_answer, status, started_at, finished_at, latency_ms, "
                "estimated_cost_usd, model_provider, model_name, retrieved_documents, evaluation_result) "
                "VALUES (:id, :scenario_id, :input, :answer, :status, :started, :finished, :latency, "
                ":cost, :provider, :model, :documents, :evaluation)"
            ),
            {
                "id": "legacy-run",
                "scenario_id": "legacy-scenario",
                "input": "hello",
                "answer": "safe",
                "status": "completed",
                "started": "2026-01-01T00:00:00+00:00",
                "finished": "2026-01-01T00:00:00+00:00",
                "latency": 10,
                "cost": 0.0,
                "provider": "mock",
                "model": "legacy",
                "documents": json.dumps([]),
                "evaluation": json.dumps({"passed": True, "score": 1.0, "severity": "medium"}),
            },
        )
        # Reproduce a real pre-Alembic database: legacy tables exist without a revision marker.
        connection.execute(sa.text("DROP TABLE alembic_version"))

    try:
        _upgrade(database_path, "head", monkeypatch)

        with engine.connect() as connection:
            migrated = (
                connection.execute(
                    sa.text(
                        "SELECT input_source, evaluation_outcome, passed, score, evaluator_version "
                        "FROM agent_runs WHERE id = 'legacy-run'"
                    )
                )
                .mappings()
                .one()
            )
        assert migrated == {
            "input_source": "scenario",
            "evaluation_outcome": "evaluated",
            "passed": 1,
            "score": 1.0,
            "evaluator_version": "legacy-v0",
        }
    finally:
        engine.dispose()

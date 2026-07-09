from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy.orm import Session, selectinload

from app.agents import AgentConfig, AgentRunner
from app.evaluation import ScenarioEvaluator
from app.models import AgentConfigModel, AgentRun, Scenario, ToolCall
from app.schemas.api import BatchRunResponse, MetricsSummary, RunListItem
from app.services.agent_config_service import AgentConfigService


class RunService:
    def __init__(self, db: Session):
        self.db = db
        self.config_service = AgentConfigService(db)
        self.evaluator = ScenarioEvaluator()

    def run_once(self, scenario_id: str | None = None, input_text: str | None = None) -> AgentRun:
        scenario = self._get_scenario(scenario_id) if scenario_id else None
        resolved_input = input_text or (scenario.input if scenario else None)
        if not resolved_input:
            raise ValueError("Either scenario_id or input must be provided")

        config = self.config_service.get_default()
        runner = AgentRunner(self.db)
        result = runner.run(resolved_input, _to_agent_config(config))
        evaluation = self.evaluator.evaluate(scenario, result)

        run = AgentRun(
            id=str(uuid.uuid4()),
            scenario_id=scenario.id if scenario else None,
            input=result.input,
            final_answer=result.final_answer,
            status=result.status,
            started_at=result.started_at,
            finished_at=result.finished_at,
            latency_ms=result.latency_ms,
            estimated_cost_usd=result.estimated_cost_usd,
            model_provider=result.model_provider,
            model_name=result.model_name,
            retrieved_documents=result.retrieved_documents,
            evaluation_result=evaluation.model_dump(),
        )
        self.db.add(run)
        self.db.flush()

        for trace in result.tool_calls:
            self.db.add(
                ToolCall(
                    run_id=run.id,
                    tool_name=trace.tool_name,
                    input=trace.input,
                    output=trace.output,
                    started_at=trace.started_at,
                    finished_at=trace.finished_at,
                    latency_ms=trace.latency_ms,
                    error=trace.error,
                )
            )

        self.db.commit()
        return self.get_run(run.id)

    def run_batch(self, scenario_ids: list[str] | None = None) -> BatchRunResponse:
        scenarios = self._get_scenarios(scenario_ids)
        runs = [self.run_once(scenario_id=scenario.id) for scenario in scenarios]
        items = [to_run_list_item(run) for run in runs]
        average_score = round(sum(item.score for item in items) / len(items), 3) if items else 0.0
        pass_rate = round(sum(1 for item in items if item.passed) / len(items), 3) if items else 0.0
        return BatchRunResponse(
            run_ids=[run.id for run in runs],
            results=items,
            average_score=average_score,
            pass_rate=pass_rate,
        )

    def list_runs(self, limit: int = 100) -> list[AgentRun]:
        return (
            self.db.query(AgentRun)
            .options(selectinload(AgentRun.tool_calls))
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
            .all()
        )

    def get_run(self, run_id: str) -> AgentRun:
        run = (
            self.db.query(AgentRun)
            .options(selectinload(AgentRun.tool_calls))
            .filter(AgentRun.id == run_id)
            .one_or_none()
        )
        if run is None:
            raise LookupError(f"Run not found: {run_id}")
        return run

    def metrics_summary(self) -> MetricsSummary:
        runs = self.list_runs(limit=500)
        latest_runs = runs[:20]
        total_runs = len(runs)
        latest_pass_rate = (
            round(sum(1 for run in latest_runs if _passed(run)) / len(latest_runs), 3) if latest_runs else 0.0
        )
        critical_failures = sum(
            1
            for run in runs
            if not _passed(run) and run.evaluation_result.get("severity") == "critical"
        )
        average_latency_ms = round(sum(run.latency_ms for run in runs) / total_runs, 1) if total_runs else 0.0
        reasons = [
            reason
            for run in runs
            for reason in run.evaluation_result.get("failure_reasons", [])
        ]
        most_common = Counter(reasons).most_common(1)
        return MetricsSummary(
            total_runs=total_runs,
            latest_pass_rate=latest_pass_rate,
            critical_failures=critical_failures,
            average_latency_ms=average_latency_ms,
            most_common_failure_reason=most_common[0][0] if most_common else None,
        )

    def _get_scenario(self, scenario_id: str) -> Scenario:
        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).one_or_none()
        if scenario is None:
            raise LookupError(f"Scenario not found: {scenario_id}")
        return scenario

    def _get_scenarios(self, scenario_ids: list[str] | None) -> list[Scenario]:
        query = self.db.query(Scenario)
        if scenario_ids:
            scenarios = query.filter(Scenario.id.in_(scenario_ids)).all()
            found = {scenario.id for scenario in scenarios}
            missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in found]
            if missing:
                raise LookupError(f"Scenarios not found: {', '.join(missing)}")
            return sorted(scenarios, key=lambda scenario: scenario_ids.index(scenario.id))
        return query.order_by(Scenario.id).all()


def to_run_list_item(run: AgentRun) -> RunListItem:
    return RunListItem(
        id=run.id,
        scenario_id=run.scenario_id,
        status=run.status,
        started_at=run.started_at,
        latency_ms=run.latency_ms,
        estimated_cost_usd=run.estimated_cost_usd,
        model_provider=run.model_provider,
        passed=_passed(run),
        score=float(run.evaluation_result.get("score", 0.0)),
        failure_reasons=list(run.evaluation_result.get("failure_reasons", [])),
    )


def _to_agent_config(config: AgentConfigModel) -> AgentConfig:
    return AgentConfig(
        agent_name=config.agent_name,
        system_prompt=config.system_prompt,
        model_mode=config.model_mode,
        temperature=config.temperature,
        max_tool_calls=config.max_tool_calls,
    )


def _passed(run: AgentRun) -> bool:
    return bool(run.evaluation_result.get("passed", False))


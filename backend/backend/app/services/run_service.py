from __future__ import annotations

import hashlib
import inspect
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import Session, selectinload

from app.agents import AgentConfig, AgentRunner
from app.agents.providers import ProviderException
from app.agents.targets import NovaCartTarget
from app.evaluation import ScenarioEvaluator
from app.evaluation.semantic_judge import SemanticJudge
from app.models import (
    AgentConfigModel,
    AgentRun,
    BatchRun,
    EvaluationCheckRecord,
    Scenario,
    Suite,
    ToolCall,
)
from app.schemas.api import (
    BaselineComparison,
    BaselineComparisonItem,
    BatchPage,
    BatchRunResponse,
    MetricsSummary,
    RunListItem,
    RunPage,
)
from app.services.agent_config_service import AgentConfigService
from app.services.redaction import DEFAULT_SENSITIVE_KEYS, redact_sensitive

RunnerFactory = Callable[[Session], AgentRunner]


class RunService:
    def __init__(
        self,
        db: Session,
        *,
        runner_factory: RunnerFactory = AgentRunner,
        evaluator: ScenarioEvaluator | None = None,
        semantic_judge: SemanticJudge | None = None,
        sensitive_keys: set[str] | frozenset[str] = DEFAULT_SENSITIVE_KEYS,
        pricing_metadata: dict[str, Any] | None = None,
    ):
        self.db = db
        self.config_service = AgentConfigService(db)
        self.evaluator = evaluator or ScenarioEvaluator()
        self.semantic_judge = semantic_judge
        self.runner_factory = runner_factory
        self.sensitive_keys = sensitive_keys
        self.pricing_metadata = dict(pricing_metadata or {})

    def run_once(
        self,
        scenario_id: str | None = None,
        input_text: str | None = None,
        *,
        mode: str | None = None,
        evaluation_spec_scenario_id: str | None = None,
        batch_id: str | None = None,
        repetition_index: int = 0,
        config_override: AgentConfigModel | None = None,
    ) -> AgentRun:
        source_scenario = self._get_scenario(scenario_id) if scenario_id else None
        input_source = self._resolve_input_source(mode, source_scenario, input_text)
        resolved_input = self._resolve_input(input_source, source_scenario, input_text)
        evaluation_scenario = self._evaluation_scenario(
            input_source=input_source,
            source_scenario=source_scenario,
            evaluation_spec_scenario_id=evaluation_spec_scenario_id,
        )
        config = config_override or self.config_service.get_default()
        sensitive_values = (config.system_prompt,)
        snapshot_scenario = source_scenario or evaluation_scenario
        scenario_snapshot = _scenario_snapshot(snapshot_scenario, resolved_input, input_source)
        if source_scenario is None and evaluation_scenario is not None:
            scenario_snapshot["evaluation_only"] = True
        evaluation_spec_snapshot = (
            dict(evaluation_scenario.evaluation_spec) if evaluation_scenario is not None else {}
        )
        tool_version, tool_definitions = _tool_snapshot(self.db, config.max_tool_calls)
        agent_snapshot = _agent_snapshot(config)
        started_at = datetime.now(UTC)

        run = AgentRun(
            id=str(uuid.uuid4()),
            scenario_id=source_scenario.id
            if source_scenario and input_source != "ad_hoc"
            else None,
            evaluation_spec_scenario_id=(
                evaluation_scenario.id
                if evaluation_scenario is not None and evaluation_scenario is not source_scenario
                else None
            ),
            batch_id=batch_id,
            repetition_index=repetition_index,
            input_source=input_source,
            input=resolved_input,
            final_answer=None,
            status="running",
            started_at=started_at,
            finished_at=None,
            latency_ms=None,
            estimated_cost_usd=None,
            cost_usd=None,
            pricing_snapshot=dict(self.pricing_metadata),
            model_provider=config.model_mode,
            model_name=config.model_name or _default_model_name(config.model_mode),
            provider_version="unknown",
            provider_error=None,
            fallback_reason=None,
            evaluator_version=getattr(self.evaluator, "version", "unknown"),
            tool_version=tool_version,
            agent_name=config.agent_name,
            system_prompt_hash=agent_snapshot["system_prompt_hash"],
            system_prompt_version=str(config.version),
            temperature=config.temperature,
            max_tool_calls=config.max_tool_calls,
            scenario_snapshot=scenario_snapshot,
            evaluation_spec_snapshot=evaluation_spec_snapshot,
            agent_config_snapshot=agent_snapshot,
            tool_definitions_snapshot=tool_definitions,
            evaluation_outcome="not_evaluated",
            passed=None,
            score=None,
            severity=evaluation_scenario.severity if evaluation_scenario is not None else "ad_hoc",
            evaluation_result=_not_evaluated_result(
                severity=evaluation_scenario.severity
                if evaluation_scenario is not None
                else "ad_hoc",
                evaluator_version=getattr(self.evaluator, "version", "unknown"),
            ),
        )
        self.db.add(run)
        self.db.commit()

        monotonic_start = time.perf_counter()
        try:
            result = self.runner_factory(self.db).run(resolved_input, _to_agent_config(config))
        except ProviderException as exc:
            return self._record_execution_failure(
                run.id, exc.error.model_dump(mode="json"), monotonic_start, sensitive_values
            )
        except Exception as exc:
            error = {"category": "unknown", "message": str(exc), "retryable": False}
            return self._record_execution_failure(run.id, error, monotonic_start, sensitive_values)

        stored_run = self.db.get(AgentRun, run.id)
        if stored_run is None:
            raise RuntimeError("Run disappeared while it was executing")
        run = stored_run
        run.input = result.input
        run.final_answer = _redact(result.final_answer, self.sensitive_keys, sensitive_values)
        run.status = _normalized_status(result.status)
        run.started_at = result.started_at
        run.finished_at = result.finished_at
        run.latency_ms = result.latency_ms
        run.estimated_cost_usd = getattr(result, "estimated_cost_usd", None)
        run.cost_usd = getattr(result, "cost_usd", run.estimated_cost_usd)
        usage = getattr(result, "usage", None)
        run.input_tokens = getattr(usage, "input_tokens", None)
        run.output_tokens = getattr(usage, "output_tokens", None)
        run.total_tokens = getattr(usage, "total_tokens", None)
        run.model_provider = result.model_provider
        run.model_name = result.model_name
        run.provider_version = getattr(result, "provider_version", "unknown")
        provider_error = getattr(result, "provider_error", None)
        run.provider_error = (
            _redact(provider_error.model_dump(mode="json"), self.sensitive_keys, sensitive_values)
            if provider_error
            else None
        )
        run.fallback_reason = _redact(
            getattr(result, "fallback_reason", None), self.sensitive_keys, sensitive_values
        )
        run.messages = _redact(
            [message.model_dump(mode="json") for message in getattr(result, "messages", [])],
            self.sensitive_keys,
            sensitive_values,
        )
        run.retrieved_documents = _redact(
            result.retrieved_documents, self.sensitive_keys, sensitive_values
        )

        self._replace_tool_calls(run, result.tool_calls, sensitive_values)
        if run.status == "failed":
            evaluation = _not_evaluated_result(
                severity=run.severity,
                evaluator_version=getattr(self.evaluator, "version", "unknown"),
                reason="Provider execution failed",
            )
        elif evaluation_scenario is None:
            evaluation = _not_evaluated_result(
                severity="ad_hoc",
                evaluator_version=getattr(self.evaluator, "version", "unknown"),
            )
        else:
            try:
                evaluate_kwargs: dict[str, Any] = {}
                if "protected_content" in inspect.signature(self.evaluator.evaluate).parameters:
                    evaluate_kwargs["protected_content"] = [config.system_prompt]
                if "expected_behavior" in inspect.signature(self.evaluator.evaluate).parameters:
                    evaluate_kwargs["expected_behavior"] = evaluation_scenario.expected_behavior
                if "semantic_judge" in inspect.signature(self.evaluator.evaluate).parameters:
                    evaluate_kwargs["semantic_judge"] = self.semantic_judge
                evaluation_model = self.evaluator.evaluate(
                    evaluation_scenario, result, **evaluate_kwargs
                )
                evaluation = _normalize_evaluation_result(
                    evaluation_model.model_dump(mode="json"),
                    severity=evaluation_scenario.severity,
                    evaluator_version=getattr(self.evaluator, "version", "unknown"),
                )
            except Exception as exc:
                if run.status == "completed":
                    run.status = "degraded"
                evaluation = _evaluation_error_result(
                    severity=evaluation_scenario.severity,
                    evaluator_version=getattr(self.evaluator, "version", "unknown"),
                    error=str(exc),
                )
        self._store_evaluation(run, evaluation, sensitive_values)
        self.db.commit()
        return self.get_run(run.id)

    def run_batch(
        self,
        scenario_ids: list[str] | None = None,
        *,
        suite_id: str | None = None,
        repetitions: int = 1,
        baseline_batch_id: str | None = None,
    ) -> BatchRunResponse:
        """Persist a queued batch and return immediately."""
        if repetitions < 1 or repetitions > 20:
            raise ValueError("repetitions must be between 1 and 20")
        scenarios = self._batch_scenarios(scenario_ids=scenario_ids, suite_id=suite_id)
        resolved_baseline_id = self._resolve_baseline_batch_id(suite_id, baseline_batch_id)
        baseline = self._get_batch_model(resolved_baseline_id) if resolved_baseline_id else None
        baseline_by_scenario = _aggregate_by_scenario(baseline.runs) if baseline else {}
        config = self.config_service.get_default()
        now = datetime.now(UTC)
        batch = BatchRun(
            id=str(uuid.uuid4()),
            suite_id=suite_id,
            status="queued",
            repetitions=repetitions,
            total_runs=len(scenarios) * repetitions,
            configuration_snapshot={
                **_agent_snapshot(config),
                "pricing": dict(self.pricing_metadata),
                "baseline_batch_id": resolved_baseline_id,
                "baseline_scores": {
                    scenario_id: values.get("score")
                    for scenario_id, values in baseline_by_scenario.items()
                },
                "baseline_average_score": _average_scores(baseline.runs) if baseline else None,
                "baseline_pass_rate": _pass_rate(baseline.runs) if baseline else None,
            },
            selected_scenarios_snapshot=[
                _scenario_snapshot(item, item.input, "scenario") for item in scenarios
            ],
            created_at=now,
            queued_at=now,
        )
        self.db.add(batch)
        self.db.commit()
        return to_batch_response(batch)

    def execute_batch(self, batch_id: str, *, worker_id: str) -> BatchRunResponse:
        batch = self._get_batch_model(batch_id)
        if batch.status == "cancelled":
            return to_batch_response(batch)
        if batch.status not in {"queued", "running", "cancelling"}:
            return to_batch_response(batch)
        if batch.status == "queued":
            batch.status = "running"
            batch.started_at = datetime.now(UTC)
        batch.worker_id = worker_id
        batch.last_heartbeat_at = datetime.now(UTC)
        self.db.commit()
        config = self.config_service.get_default()
        snapshots = list(batch.selected_scenarios_snapshot)
        for repetition_index in range(batch.repetitions):
            for snapshot in snapshots:
                self.db.refresh(batch)
                if batch.status in {"cancelling", "cancelled"}:
                    return to_batch_response(self._finalize_cancelled_batch(batch.id))
                scenario_id = str(snapshot.get("id") or "")
                already = (
                    self.db.query(AgentRun)
                    .filter(
                        AgentRun.batch_id == batch.id,
                        AgentRun.scenario_id == scenario_id,
                        AgentRun.repetition_index == repetition_index,
                    )
                    .first()
                )
                if already is not None:
                    continue
                self.run_once(
                    scenario_id=scenario_id,
                    mode="scenario",
                    batch_id=batch.id,
                    repetition_index=repetition_index,
                    config_override=config,
                )
                batch.last_heartbeat_at = datetime.now(UTC)
                self._refresh_batch_progress(batch.id)
        return to_batch_response(self._finalize_batch(batch.id))

    def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        scenario_id: str | None = None,
        batch_id: str | None = None,
        status: str | None = None,
        model_provider: str | None = None,
        input_source: str | None = None,
        severity: str | None = None,
        query: str | None = None,
        passed: bool | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        limit: int | None = None,
    ) -> RunPage:
        if limit is not None:
            page = 1
            page_size = limit
        if page < 1 or page_size < 1 or page_size > 500:
            raise ValueError("Invalid pagination values")
        search_query = query
        runs_query = self.db.query(AgentRun)
        if scenario_id is not None:
            runs_query = runs_query.filter(AgentRun.scenario_id == scenario_id)
        if batch_id is not None:
            runs_query = runs_query.filter(AgentRun.batch_id == batch_id)
        if status is not None:
            runs_query = runs_query.filter(AgentRun.status == status)
        if model_provider is not None:
            runs_query = runs_query.filter(AgentRun.model_provider == model_provider)
        if input_source is not None:
            runs_query = runs_query.filter(AgentRun.input_source == input_source)
        if severity is not None:
            runs_query = runs_query.filter(AgentRun.severity == severity)
        if search_query is not None:
            normalized_query = search_query.strip()
            if len(normalized_query) > 200:
                raise ValueError("query must be at most 200 characters")
            if normalized_query:
                escaped = (
                    normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                pattern = f"%{escaped}%"
                runs_query = runs_query.filter(
                    or_(
                        AgentRun.input.ilike(pattern, escape="\\"),
                        cast(AgentRun.scenario_snapshot, String).ilike(pattern, escape="\\"),
                    )
                )
        if passed is not None:
            runs_query = runs_query.filter(AgentRun.passed.is_(passed))
        if started_after is not None:
            runs_query = runs_query.filter(AgentRun.started_at >= started_after)
        if started_before is not None:
            runs_query = runs_query.filter(AgentRun.started_at <= started_before)

        total = runs_query.order_by(None).count()
        pages = math.ceil(total / page_size) if total else 0
        runs = (
            runs_query.order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return RunPage(
            items=[to_run_list_item(run) for run in runs],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            next_cursor=str(page + 1) if page < pages else None,
        )

    def get_run(self, run_id: str) -> AgentRun:
        run = (
            self.db.query(AgentRun)
            .options(selectinload(AgentRun.tool_calls), selectinload(AgentRun.evaluation_checks))
            .filter(AgentRun.id == run_id)
            .one_or_none()
        )
        if run is None:
            raise LookupError(f"Run not found: {run_id}")
        return run

    def get_batch(self, batch_id: str) -> BatchRunResponse:
        batch = self._get_batch_model(batch_id)
        return to_batch_response(batch)

    def list_batches(
        self, *, page: int = 1, page_size: int = 50, status: str | None = None
    ) -> BatchPage:
        if page < 1 or page_size < 1 or page_size > 200:
            raise ValueError("Invalid pagination values")
        query = self.db.query(BatchRun)
        if status is not None:
            query = query.filter(BatchRun.status == status)
        total = query.order_by(None).count()
        batches = (
            query.options(selectinload(BatchRun.runs))
            .order_by(BatchRun.created_at.desc(), BatchRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return BatchPage(
            items=[to_batch_response(batch) for batch in batches],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    def cancel_batch(self, batch_id: str) -> BatchRunResponse:
        batch = self._get_batch_model(batch_id)
        if batch.status in {"cancelled", "cancelling"}:
            return to_batch_response(batch)
        if batch.status == "queued":
            batch.status = "cancelled"
            batch.cancelled_runs = batch.total_runs
            batch.finished_at = datetime.now(UTC)
        elif batch.status == "running":
            batch.status = "cancelling"
        else:
            raise ValueError("Batch is already terminal and cannot be cancelled")
        self.db.commit()
        return to_batch_response(batch)

    def compare_batches(self, current_batch_id: str, baseline_batch_id: str) -> BaselineComparison:
        current = self._get_batch_model(current_batch_id)
        baseline = self._get_batch_model(baseline_batch_id)
        current_by_scenario = _aggregate_by_scenario(current.runs)
        baseline_by_scenario = _aggregate_by_scenario(baseline.runs)
        scenario_ids = sorted(set(current_by_scenario) | set(baseline_by_scenario))
        items: list[BaselineComparisonItem] = []
        for scenario_id in scenario_ids:
            current_value = current_by_scenario.get(scenario_id, {})
            baseline_value = baseline_by_scenario.get(scenario_id, {})
            current_score = current_value.get("score")
            baseline_score = baseline_value.get("score")
            items.append(
                BaselineComparisonItem(
                    scenario_id=scenario_id,
                    baseline_score=baseline_score,
                    current_score=current_score,
                    score_delta=_delta(current_score, baseline_score),
                    baseline_passed=baseline_value.get("passed"),
                    current_passed=current_value.get("passed"),
                )
            )
        return BaselineComparison(
            baseline_batch_id=baseline.id,
            current_batch_id=current.id,
            score_delta=_delta(_average_scores(current.runs), _average_scores(baseline.runs)),
            pass_rate_delta=_delta(_pass_rate(current.runs), _pass_rate(baseline.runs)),
            scenarios=items,
        )

    def metrics_summary(self) -> MetricsSummary:
        totals = self.db.query(
            func.count(AgentRun.id),
            func.sum(case((AgentRun.evaluation_outcome == "evaluated", 1), else_=0)),
            func.sum(case((AgentRun.evaluation_outcome == "not_evaluated", 1), else_=0)),
            func.sum(
                case(
                    ((AgentRun.passed.is_(False)) & (AgentRun.severity == "critical"), 1),
                    else_=0,
                )
            ),
            func.avg(AgentRun.latency_ms),
            func.sum(AgentRun.cost_usd),
            func.sum(AgentRun.total_tokens),
        ).one()
        latest_evaluated = (
            self.db.query(AgentRun.passed.label("passed"))
            .filter(AgentRun.evaluation_outcome == "evaluated", AgentRun.passed.is_not(None))
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(20)
            .subquery()
        )
        latest_pass_rate = self.db.query(
            func.avg(case((latest_evaluated.c.passed.is_(True), 1.0), else_=0.0))
        ).scalar()
        common_failure = (
            self.db.query(
                EvaluationCheckRecord.label, func.count(EvaluationCheckRecord.id).label("count")
            )
            .filter(EvaluationCheckRecord.passed.is_(False))
            .group_by(EvaluationCheckRecord.label)
            .order_by(func.count(EvaluationCheckRecord.id).desc(), EvaluationCheckRecord.label)
            .first()
        )
        return MetricsSummary(
            total_runs=int(totals[0] or 0),
            evaluated_runs=int(totals[1] or 0),
            not_evaluated_runs=int(totals[2] or 0),
            latest_pass_rate=round(float(latest_pass_rate or 0.0), 3),
            critical_failures=int(totals[3] or 0),
            average_latency_ms=round(float(totals[4] or 0.0), 1),
            total_cost_usd=round(float(totals[5] or 0.0), 8),
            total_tokens=int(totals[6] or 0),
            most_common_failure_reason=common_failure[0] if common_failure else None,
        )

    def _record_execution_failure(
        self,
        run_id: str,
        provider_error: dict[str, Any],
        monotonic_start: float,
        sensitive_values: tuple[str, ...],
    ) -> AgentRun:
        self.db.rollback()
        run = self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Run disappeared while recording a provider failure")
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.latency_ms = int((time.perf_counter() - monotonic_start) * 1000)
        run.provider_error = _redact(provider_error, self.sensitive_keys, sensitive_values)
        run.evaluation_result = _not_evaluated_result(
            severity=run.severity,
            evaluator_version=getattr(self.evaluator, "version", "unknown"),
            reason="Provider execution failed",
        )
        self._store_evaluation(run, run.evaluation_result, sensitive_values)
        self.db.commit()
        return self.get_run(run.id)

    def _replace_tool_calls(
        self, run: AgentRun, traces: list[Any], sensitive_values: tuple[str, ...]
    ) -> None:
        run.tool_calls.clear()
        for sequence_index, trace in enumerate(traces):
            run.tool_calls.append(
                ToolCall(
                    sequence_index=sequence_index,
                    tool_name=trace.tool_name,
                    input=_redact(trace.input, self.sensitive_keys, sensitive_values),
                    output=_redact(trace.output, self.sensitive_keys, sensitive_values),
                    started_at=trace.started_at,
                    finished_at=trace.finished_at,
                    latency_ms=trace.latency_ms,
                    error=_redact(trace.error, self.sensitive_keys, sensitive_values),
                )
            )

    def _store_evaluation(
        self, run: AgentRun, evaluation: dict[str, Any], sensitive_values: tuple[str, ...]
    ) -> None:
        run.evaluation_result = _redact(evaluation, self.sensitive_keys, sensitive_values)
        run.evaluation_outcome = str(evaluation["outcome"])
        run.passed = evaluation.get("passed")
        run.score = evaluation.get("score")
        run.severity = str(evaluation.get("severity", run.severity))
        run.evaluator_version = str(
            evaluation.get("evaluator_version", run.evaluator_version or "unknown")
        )
        run.evaluation_checks.clear()
        for check in evaluation.get("checks", []):
            run.evaluation_checks.append(
                EvaluationCheckRecord(
                    check_id=str(check["check_id"]),
                    label=str(check["label"]),
                    passed=bool(check["passed"]),
                    contribution=float(check.get("contribution", 0.0)),
                    max_contribution=float(check.get("max_contribution", 0.0)),
                    dimension=str(check.get("dimension", "policy_compliance")),
                    hard_failure=bool(check.get("hard_failure", False)),
                    evidence=str(
                        _redact(check.get("evidence", ""), self.sensitive_keys, sensitive_values)
                    ),
                )
            )

    def _refresh_batch_progress(self, batch_id: str) -> None:
        batch = self.db.get(BatchRun, batch_id)
        if batch is None:
            raise LookupError(f"Batch not found: {batch_id}")
        count_rows = (
            self.db.query(AgentRun.status, func.count(AgentRun.id))
            .filter(AgentRun.batch_id == batch_id)
            .group_by(AgentRun.status)
            .all()
        )
        counts: dict[str, int] = {str(row[0]): int(row[1]) for row in count_rows}
        batch.completed_runs = int(counts.get("completed", 0))
        batch.failed_runs = int(counts.get("failed", 0))
        batch.degraded_runs = int(counts.get("degraded", 0))
        batch.cancelled_runs = int(counts.get("cancelled", 0))
        self.db.commit()

    def _finalize_batch(self, batch_id: str) -> BatchRun:
        batch = self._get_batch_model(batch_id)
        if batch.status in {"cancelling", "cancelled"}:
            return self._finalize_cancelled_batch(batch_id)
        if batch.failed_runs == batch.total_runs and batch.total_runs > 0:
            batch.status = "failed"
        elif batch.failed_runs or batch.degraded_runs:
            batch.status = "degraded"
        else:
            batch.status = "completed"
        batch.finished_at = datetime.now(UTC)
        average_score = _average_scores(batch.runs)
        pass_rate = _pass_rate(batch.runs)
        baseline_average = batch.configuration_snapshot.get("baseline_average_score")
        baseline_pass_rate = batch.configuration_snapshot.get("baseline_pass_rate")
        batch.aggregate_result = {
            "average_score": average_score,
            "pass_rate": pass_rate,
            "score_delta": _delta(average_score, baseline_average),
            "pass_rate_delta": _delta(pass_rate, baseline_pass_rate),
            "baseline_batch_id": batch.configuration_snapshot.get("baseline_batch_id"),
            "evaluated_runs": sum(run.evaluation_outcome == "evaluated" for run in batch.runs),
            "not_evaluated_runs": sum(run.evaluation_outcome != "evaluated" for run in batch.runs),
            "failed_runs": batch.failed_runs,
            "degraded_runs": batch.degraded_runs,
        }
        self.db.commit()
        return self._get_batch_model(batch_id)

    def _finalize_cancelled_batch(self, batch_id: str) -> BatchRun:
        batch = self._get_batch_model(batch_id)
        processed = batch.completed_runs + batch.failed_runs + batch.degraded_runs
        batch.cancelled_runs = max(batch.cancelled_runs, batch.total_runs - processed)
        batch.status = "cancelled"
        batch.finished_at = datetime.now(UTC)
        batch.aggregate_result = {
            "average_score": _average_scores(batch.runs),
            "pass_rate": _pass_rate(batch.runs),
            "cancelled_runs": batch.cancelled_runs,
        }
        self.db.commit()
        return self._get_batch_model(batch_id)

    def _get_batch_model(self, batch_id: str) -> BatchRun:
        batch = (
            self.db.query(BatchRun)
            .options(selectinload(BatchRun.runs))
            .filter(BatchRun.id == batch_id)
            .one_or_none()
        )
        if batch is None:
            raise LookupError(f"Batch not found: {batch_id}")
        return batch

    def _get_scenario(self, scenario_id: str | None) -> Scenario:
        if not scenario_id:
            raise LookupError("Scenario ID is required")
        scenario = self.db.get(Scenario, scenario_id)
        if scenario is None:
            raise LookupError(f"Scenario not found: {scenario_id}")
        if scenario.archived_at is not None:
            raise ValueError(f"Scenario is archived: {scenario_id}")
        return scenario

    def _get_scenarios(self, scenario_ids: list[str] | None) -> list[Scenario]:
        query = self.db.query(Scenario).filter(Scenario.archived_at.is_(None))
        if scenario_ids:
            scenarios = query.filter(Scenario.id.in_(scenario_ids)).all()
            found = {scenario.id: scenario for scenario in scenarios}
            missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in found]
            if missing:
                raise LookupError(f"Scenarios not found: {', '.join(missing)}")
            return [found[scenario_id] for scenario_id in scenario_ids]
        return query.order_by(Scenario.id).all()

    def _resolve_baseline_batch_id(
        self, suite_id: str | None, requested_baseline_id: str | None
    ) -> str | None:
        if requested_baseline_id:
            baseline = self._get_batch_model(requested_baseline_id)
            if baseline.status == "running":
                raise ValueError("A running batch cannot be used as a baseline")
            return baseline.id
        if not suite_id:
            return None
        suite = self.db.get(Suite, suite_id)
        if suite is None:
            raise LookupError(f"Suite not found: {suite_id}")
        if not suite.baseline_batch_id:
            return None
        baseline = self._get_batch_model(suite.baseline_batch_id)
        if baseline.status == "running":
            raise ValueError("A running batch cannot be used as a baseline")
        return baseline.id

    def _batch_scenarios(
        self, *, scenario_ids: list[str] | None, suite_id: str | None
    ) -> list[Scenario]:
        if suite_id is None:
            return self._get_scenarios(scenario_ids)
        if scenario_ids is not None:
            raise ValueError("Choose scenario_ids or suite_id, not both")
        suite = (
            self.db.query(Suite)
            .options(selectinload(Suite.scenario_links))
            .filter(Suite.id == suite_id)
            .one_or_none()
        )
        if suite is None:
            raise LookupError(f"Suite not found: {suite_id}")
        if suite.archived_at is not None:
            raise ValueError(f"Suite is archived: {suite_id}")
        return self._get_scenarios([link.scenario_id for link in suite.scenario_links])

    @staticmethod
    def _resolve_input_source(
        mode: str | None, scenario: Scenario | None, input_text: str | None
    ) -> str:
        if mode is not None:
            if mode not in {"scenario", "mutation", "ad_hoc"}:
                raise ValueError(f"Unsupported run mode: {mode}")
            return mode
        if scenario is None:
            return "ad_hoc"
        if input_text is not None and input_text != scenario.input:
            return "mutation"
        return "scenario"

    @staticmethod
    def _resolve_input(input_source: str, scenario: Scenario | None, input_text: str | None) -> str:
        if input_source == "scenario":
            if scenario is None:
                raise ValueError("scenario mode requires scenario_id")
            if input_text is not None and input_text != scenario.input:
                raise ValueError(
                    "scenario mode uses the immutable stored input; choose mutation mode to edit it"
                )
            return scenario.input
        if input_source == "mutation":
            if scenario is None or not input_text:
                raise ValueError("mutation mode requires scenario_id and input")
            return input_text
        if scenario is not None:
            raise ValueError(
                "ad_hoc mode cannot include scenario_id; use evaluation_spec_scenario_id"
            )
        if not input_text:
            raise ValueError("ad_hoc mode requires input")
        return input_text

    def _evaluation_scenario(
        self,
        *,
        input_source: str,
        source_scenario: Scenario | None,
        evaluation_spec_scenario_id: str | None,
    ) -> Scenario | None:
        if input_source in {"scenario", "mutation"}:
            if evaluation_spec_scenario_id and (
                source_scenario is None or evaluation_spec_scenario_id != source_scenario.id
            ):
                raise ValueError(
                    "Scenario and mutation modes use the selected scenario's evaluation specification"
                )
            return source_scenario
        return (
            self._get_scenario(evaluation_spec_scenario_id) if evaluation_spec_scenario_id else None
        )


def to_run_list_item(
    run: AgentRun, baseline_scores: dict[str, float | None] | None = None
) -> RunListItem:
    evaluation = run.evaluation_result or {}
    scenario_name = run.scenario_snapshot.get("name") if run.scenario_snapshot else None
    return RunListItem(
        id=run.id,
        scenario_id=run.scenario_id,
        scenario_name=str(scenario_name) if scenario_name else None,
        batch_id=run.batch_id,
        input_source=run.input_source,
        input_preview=_preview(run.input),
        status=_normalized_status(run.status),
        started_at=run.started_at,
        finished_at=run.finished_at,
        latency_ms=run.latency_ms,
        model_provider=run.model_provider,
        model_name=run.model_name,
        outcome=run.evaluation_outcome,
        passed=run.passed,
        score=run.score,
        severity=run.severity,
        failure_reasons=list(evaluation.get("failure_reasons", [])),
        provider_error=run.provider_error,
        fallback_reason=run.fallback_reason,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        cost_usd=run.cost_usd,
        baseline_score_delta=_delta(
            run.score,
            (baseline_scores or {}).get(run.scenario_id or ""),
        ),
    )


def to_batch_response(batch: BatchRun) -> BatchRunResponse:
    runs = list(batch.runs)
    raw_baseline_scores = batch.configuration_snapshot.get("baseline_scores", {})
    baseline_scores = (
        {
            str(scenario_id): float(score) if score is not None else None
            for scenario_id, score in raw_baseline_scores.items()
        }
        if isinstance(raw_baseline_scores, dict)
        else {}
    )
    average_score = (
        batch.aggregate_result.get("average_score")
        if batch.aggregate_result
        else _average_scores(runs)
    )
    pass_rate = (
        batch.aggregate_result.get("pass_rate") if batch.aggregate_result else _pass_rate(runs)
    )
    return BatchRunResponse(
        id=batch.id,
        suite_id=batch.suite_id,
        status=batch.status,
        run_ids=[run.id for run in runs],
        results=[to_run_list_item(run, baseline_scores) for run in runs],
        average_score=average_score,
        pass_rate=pass_rate,
        repetitions=batch.repetitions,
        total_runs=batch.total_runs,
        completed_runs=batch.completed_runs,
        failed_runs=batch.failed_runs,
        degraded_runs=batch.degraded_runs,
        cancelled_runs=batch.cancelled_runs,
        queued_at=batch.queued_at,
        last_heartbeat_at=batch.last_heartbeat_at,
        worker_id=batch.worker_id,
        failure_reason=batch.failure_reason,
        retry_count=batch.retry_count,
        aggregate_result=batch.aggregate_result,
        configuration_snapshot=batch.configuration_snapshot,
        selected_scenarios_snapshot=batch.selected_scenarios_snapshot,
        created_at=batch.created_at,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
    )


def _to_agent_config(config: AgentConfigModel) -> AgentConfig:
    return AgentConfig(
        agent_name=config.agent_name,
        system_prompt=config.system_prompt,
        model_mode=config.model_mode,
        model_name=config.model_name,
        temperature=config.temperature,
        max_tool_calls=config.max_tool_calls,
        system_prompt_version=config.version,
        request_timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        fallback_enabled=config.fallback_enabled,
    )


def _scenario_snapshot(
    scenario: Scenario | None, actual_input: str, input_source: str
) -> dict[str, Any]:
    if scenario is None:
        return {}
    return {
        "id": scenario.id,
        "name": scenario.name,
        "input": actual_input,
        "stored_input": scenario.input,
        "input_source": input_source,
        "severity": scenario.severity,
        "expected_behavior": scenario.expected_behavior,
        "evaluation_spec": dict(scenario.evaluation_spec),
        "evaluation_spec_version": scenario.evaluation_spec_version,
    }


def _agent_snapshot(config: AgentConfigModel) -> dict[str, Any]:
    return {
        "agent_name": config.agent_name,
        "system_prompt_hash": hashlib.sha256(config.system_prompt.encode("utf-8")).hexdigest(),
        "system_prompt_version": str(config.version),
        "model_mode": config.model_mode,
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tool_calls": config.max_tool_calls,
        "request_timeout_seconds": config.request_timeout_seconds,
        "max_retries": config.max_retries,
        "fallback_enabled": config.fallback_enabled,
    }


def _tool_snapshot(db: Session, max_tool_calls: int) -> tuple[str, list[dict[str, Any]]]:
    target = NovaCartTarget(db, max_tool_calls=max_tool_calls)
    return target.version, [
        definition.model_dump(mode="json") for definition in target.tool_definitions
    ]


def _normalize_evaluation_result(
    evaluation: dict[str, Any], *, severity: str, evaluator_version: str
) -> dict[str, Any]:
    normalized = dict(evaluation)
    normalized.setdefault("outcome", "evaluated")
    normalized.setdefault("checks", [])
    normalized.setdefault("failure_reasons", [])
    normalized.setdefault("severity", severity)
    normalized.setdefault("evaluator_version", evaluator_version)
    normalized.setdefault("evaluation_spec_version", None)
    normalized.setdefault("judge_metadata", None)
    normalized.setdefault("judge_error", None)
    return normalized


def _not_evaluated_result(
    *, severity: str, evaluator_version: str, reason: str | None = None
) -> dict[str, Any]:
    return {
        "outcome": "not_evaluated",
        "passed": None,
        "score": None,
        "tool_call_correctness": None,
        "policy_compliance": None,
        "prompt_injection_resistance": None,
        "groundedness": None,
        "checks": [],
        "failure_reasons": [reason] if reason else [],
        "severity": severity,
        "evaluation_spec_version": None,
        "evaluator_version": evaluator_version,
        "judge_metadata": None,
        "judge_error": None,
    }


def _evaluation_error_result(
    *, severity: str, evaluator_version: str, error: str
) -> dict[str, Any]:
    result = _not_evaluated_result(severity=severity, evaluator_version=evaluator_version)
    result["outcome"] = "evaluation_error"
    result["failure_reasons"] = ["Evaluation could not be completed"]
    result["judge_error"] = error
    return result


def _normalized_status(status: str) -> str:
    return (
        status
        if status in {"running", "completed", "degraded", "failed", "cancelled"}
        else "failed"
    )


def _default_model_name(model_mode: str) -> str:
    return "deterministic-novacart-v2" if model_mode == "mock" else "configured-provider-model"


def _redact(
    value: Any,
    sensitive_keys: set[str] | frozenset[str],
    sensitive_values: tuple[str, ...] = (),
) -> Any:
    return redact_sensitive(value, sensitive_keys=sensitive_keys, sensitive_values=sensitive_values)


def _preview(value: str, length: int = 180) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= length else f"{compact[: length - 1]}…"


def _average_scores(runs: list[AgentRun]) -> float | None:
    scores = [
        run.score for run in runs if run.evaluation_outcome == "evaluated" and run.score is not None
    ]
    return round(sum(scores) / len(scores), 3) if scores else None


def _pass_rate(runs: list[AgentRun]) -> float | None:
    evaluated = [
        run for run in runs if run.evaluation_outcome == "evaluated" and run.passed is not None
    ]
    return (
        round(sum(run.passed is True for run in evaluated) / len(evaluated), 3)
        if evaluated
        else None
    )


def _aggregate_by_scenario(runs: list[AgentRun]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[AgentRun]] = defaultdict(list)
    for run in runs:
        scenario_id = run.scenario_id or str(run.scenario_snapshot.get("id") or "ad_hoc")
        grouped[scenario_id].append(run)
    return {
        scenario_id: {
            "score": _average_scores(items),
            "passed": all(item.passed is True for item in items if item.passed is not None)
            if any(item.passed is not None for item in items)
            else None,
        }
        for scenario_id, items in grouped.items()
    }


def _delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 3)

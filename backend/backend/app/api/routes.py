from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.evaluation.semantic_judge import GeminiSemanticJudge, SemanticJudge
from app.schemas.api import (
    AgentConfigRead,
    AgentConfigUpdate,
    AgentRunRead,
    BaselineComparison,
    BatchPage,
    BatchRunCreate,
    BatchRunResponse,
    HealthResponse,
    MetricsSummary,
    RunCreate,
    RunPage,
    ScenarioCreate,
    ScenarioExportResponse,
    ScenarioImportRequest,
    ScenarioImportResponse,
    ScenarioRead,
    ScenarioUpdate,
    SuiteCreate,
    SuiteRead,
    SuiteUpdate,
)
from app.services import AgentConfigService, RunService, ScenarioService, SuiteService
from app.services.redaction import DEFAULT_SENSITIVE_KEYS, redact_sensitive
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        authentication_mode=settings.authentication_mode,
    )


@router.get("/scenarios", response_model=list[ScenarioRead])
def list_scenarios(
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[ScenarioRead]:
    return [
        ScenarioRead.model_validate(item)
        for item in ScenarioService(db).list(include_archived=include_archived)
    ]


@router.get("/scenarios/export", response_model=ScenarioExportResponse)
def export_scenarios(
    include_archived: bool = True,
    db: Session = Depends(get_db),
) -> ScenarioExportResponse:
    scenarios = [
        ScenarioRead.model_validate(item)
        for item in ScenarioService(db).list(include_archived=include_archived)
    ]
    return ScenarioExportResponse(exported_at=datetime.now(UTC), scenarios=scenarios)


@router.post(
    "/scenarios/import",
    response_model=ScenarioImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_scenarios(
    payload: ScenarioImportRequest,
    db: Session = Depends(get_db),
) -> ScenarioImportResponse:
    try:
        return ScenarioService(db).import_json(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/scenarios", response_model=ScenarioRead, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).create(payload))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).get(scenario_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioRead)
def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    db: Session = Depends(get_db),
) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).update(scenario_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/scenarios/{scenario_id}/duplicate",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).duplicate(scenario_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenarios/{scenario_id}/archive", response_model=ScenarioRead)
def archive_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).archive(scenario_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenarios/{scenario_id}/restore", response_model=ScenarioRead)
def restore_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioRead:
    try:
        return ScenarioRead.model_validate(ScenarioService(db).restore(scenario_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(scenario_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        ScenarioService(db).delete(scenario_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs", response_model=AgentRunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> AgentRunRead:
    service = _run_service(db)
    try:
        run = service.run_once(
            scenario_id=payload.scenario_id,
            input_text=payload.input,
            mode=payload.mode,
            evaluation_spec_scenario_id=payload.evaluation_spec_scenario_id,
        )
        return _run_read(run, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runs/batch", response_model=BatchRunResponse, status_code=status.HTTP_201_CREATED)
@router.post("/batches", response_model=BatchRunResponse, status_code=status.HTTP_201_CREATED)
def create_batch_run(payload: BatchRunCreate, db: Session = Depends(get_db)) -> BatchRunResponse:
    try:
        return _run_service(db).run_batch(
            scenario_ids=payload.scenario_ids,
            suite_id=payload.suite_id,
            repetitions=payload.repetitions,
            baseline_batch_id=payload.baseline_batch_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs", response_model=RunPage)
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    limit: int | None = Query(default=None, ge=1, le=500),
    scenario_id: str | None = None,
    batch_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    model_provider: str | None = None,
    input_source: str | None = None,
    severity: str | None = None,
    query: str | None = Query(default=None, max_length=200),
    passed: bool | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    db: Session = Depends(get_db),
) -> RunPage:
    try:
        return _run_service(db).list_runs(
            page=page,
            page_size=page_size,
            limit=limit,
            scenario_id=scenario_id,
            batch_id=batch_id,
            status=status_filter,
            model_provider=model_provider,
            input_source=input_source,
            severity=severity,
            query=query,
            passed=passed,
            started_after=started_after,
            started_before=started_before,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_id}/export")
def export_run(run_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        payload = _report_service(db).export_run(run_id)
        return JSONResponse(content=jsonable_encoder(payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunRead:
    try:
        return _run_read(_run_service(db).get_run(run_id), db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/batches", response_model=BatchPage)
def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> BatchPage:
    return _run_service(db).list_batches(page=page, page_size=page_size, status=status_filter)


@router.get("/batches/{batch_id}", response_model=BatchRunResponse)
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchRunResponse:
    try:
        return _run_service(db).get_batch(batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batches/{batch_id}/cancel", response_model=BatchRunResponse)
def cancel_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchRunResponse:
    try:
        return _run_service(db).cancel_batch(batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/batches/{batch_id}/compare/{baseline_batch_id}", response_model=BaselineComparison)
def compare_batches(
    batch_id: str,
    baseline_batch_id: str,
    db: Session = Depends(get_db),
) -> BaselineComparison:
    try:
        return _run_service(db).compare_batches(batch_id, baseline_batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/batches/{batch_id}/export")
def export_batch(batch_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        return JSONResponse(content=jsonable_encoder(_report_service(db).export_batch(batch_id)))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/batches/{batch_id}/export/junit")
def export_batch_junit(batch_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        xml = _report_service(db).export_batch_junit(batch_id)
        return Response(content=xml, media_type="application/xml")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(db: Session = Depends(get_db)) -> MetricsSummary:
    return _run_service(db).metrics_summary()


@router.get("/suites", response_model=list[SuiteRead])
def list_suites(
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[SuiteRead]:
    return SuiteService(db).list(include_archived=include_archived)


@router.post("/suites", response_model=SuiteRead, status_code=status.HTTP_201_CREATED)
def create_suite(payload: SuiteCreate, db: Session = Depends(get_db)) -> SuiteRead:
    try:
        return SuiteService(db).create(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/suites/{suite_id}", response_model=SuiteRead)
def get_suite(suite_id: str, db: Session = Depends(get_db)) -> SuiteRead:
    try:
        return SuiteService(db).get(suite_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/suites/{suite_id}", response_model=SuiteRead)
def update_suite(
    suite_id: str,
    payload: SuiteUpdate,
    db: Session = Depends(get_db),
) -> SuiteRead:
    try:
        return SuiteService(db).update(suite_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/suites/{suite_id}/archive", response_model=SuiteRead)
def archive_suite(suite_id: str, db: Session = Depends(get_db)) -> SuiteRead:
    try:
        return SuiteService(db).archive(suite_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/suites/{suite_id}/restore", response_model=SuiteRead)
def restore_suite(suite_id: str, db: Session = Depends(get_db)) -> SuiteRead:
    try:
        return SuiteService(db).restore(suite_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/suites/{suite_id}/baseline/{batch_id}", response_model=SuiteRead)
def set_suite_baseline(suite_id: str, batch_id: str, db: Session = Depends(get_db)) -> SuiteRead:
    try:
        return SuiteService(db).set_baseline(suite_id, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suite(suite_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        SuiteService(db).delete(suite_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/agent-config", response_model=AgentConfigRead)
def get_agent_config(db: Session = Depends(get_db)) -> AgentConfigRead:
    try:
        return AgentConfigRead.model_validate(AgentConfigService(db).get_default())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/agent-config", response_model=AgentConfigRead)
def update_agent_config(
    payload: AgentConfigUpdate, db: Session = Depends(get_db)
) -> AgentConfigRead:
    try:
        return AgentConfigRead.model_validate(AgentConfigService(db).update_default(payload))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _redaction_context(db: Session) -> tuple[set[str], tuple[str, ...]]:
    settings = get_settings()
    keys = set(DEFAULT_SENSITIVE_KEYS) | settings.trace_redact_key_set
    try:
        system_prompt = AgentConfigService(db).get_default().system_prompt
    except RuntimeError:
        system_prompt = ""
    return keys, (system_prompt,) if system_prompt else ()


def _run_service(db: Session) -> RunService:
    settings = get_settings()
    keys, _ = _redaction_context(db)
    return RunService(
        db,
        sensitive_keys=keys,
        semantic_judge=_semantic_judge(settings),
        pricing_metadata={
            "currency": "USD",
            "unit": "per_million_tokens",
            "provider": "google",
            "model": settings.gemini_model,
            "input_cost": settings.gemini_input_cost_per_million,
            "output_cost": settings.gemini_output_cost_per_million,
        },
    )


def _report_service(db: Session) -> ReportService:
    keys, values = _redaction_context(db)
    return ReportService(db, sensitive_keys=keys, sensitive_values=values)


def _run_read(run: Any, db: Session) -> AgentRunRead:
    keys, values = _redaction_context(db)
    payload = AgentRunRead.model_validate(run).model_dump(mode="json")
    snapshot = payload.get("scenario_snapshot")
    if not payload.get("scenario_name") and isinstance(snapshot, dict):
        snapshot_name = snapshot.get("name")
        if isinstance(snapshot_name, str) and snapshot_name.strip():
            payload["scenario_name"] = snapshot_name
    encoded = jsonable_encoder(payload)
    redacted = redact_sensitive(encoded, sensitive_keys=keys, sensitive_values=values)
    return AgentRunRead.model_validate(redacted)


def _semantic_judge(settings: Any) -> SemanticJudge | None:
    if settings.semantic_judge_provider == "disabled":
        return None
    if settings.semantic_judge_provider == "gemini":
        return GeminiSemanticJudge(
            api_key=settings.semantic_judge_api_key or "",
            model=settings.semantic_judge_model,
            timeout_seconds=settings.semantic_judge_timeout_seconds,
        )
    raise RuntimeError(f"Unsupported semantic judge provider: {settings.semantic_judge_provider}")

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Scenario
from app.schemas.api import (
    AgentConfigRead,
    AgentConfigUpdate,
    AgentRunRead,
    BatchRunCreate,
    BatchRunResponse,
    HealthResponse,
    MetricsSummary,
    RunCreate,
    RunListItem,
    ScenarioRead,
)
from app.services import AgentConfigService, RunService
from app.services.run_service import to_run_list_item

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name)


@router.get("/scenarios", response_model=list[ScenarioRead])
def list_scenarios(db: Session = Depends(get_db)) -> list[Scenario]:
    return db.query(Scenario).order_by(Scenario.id).all()


@router.post("/runs", response_model=AgentRunRead)
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> AgentRunRead:
    service = RunService(db)
    try:
        return service.run_once(scenario_id=payload.scenario_id, input_text=payload.input)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runs/batch", response_model=BatchRunResponse)
def create_batch_run(payload: BatchRunCreate, db: Session = Depends(get_db)) -> BatchRunResponse:
    service = RunService(db)
    try:
        return service.run_batch(scenario_ids=payload.scenario_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs", response_model=list[RunListItem])
def list_runs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[RunListItem]:
    service = RunService(db)
    return [to_run_list_item(run) for run in service.list_runs(limit=limit)]


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunRead:
    service = RunService(db)
    try:
        return service.get_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(db: Session = Depends(get_db)) -> MetricsSummary:
    return RunService(db).metrics_summary()


@router.get("/agent-config", response_model=AgentConfigRead)
def get_agent_config(db: Session = Depends(get_db)) -> AgentConfigRead:
    try:
        return AgentConfigService(db).get_default()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/agent-config", response_model=AgentConfigRead)
def update_agent_config(payload: AgentConfigUpdate, db: Session = Depends(get_db)) -> AgentConfigRead:
    try:
        return AgentConfigService(db).update_default(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


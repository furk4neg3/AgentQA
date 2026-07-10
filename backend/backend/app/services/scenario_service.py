from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation import EvaluationSpecification
from app.models import Scenario
from app.schemas.api import (
    ScenarioCreate,
    ScenarioImportRequest,
    ScenarioImportResponse,
    ScenarioUpdate,
)


class ScenarioService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, *, include_archived: bool = False) -> list[Scenario]:
        query = self.db.query(Scenario)
        if not include_archived:
            query = query.filter(Scenario.archived_at.is_(None))
        return query.order_by(Scenario.id).all()

    def get(self, scenario_id: str) -> Scenario:
        scenario = self.db.get(Scenario, scenario_id)
        if scenario is None:
            raise LookupError(f"Scenario not found: {scenario_id}")
        return scenario

    def create(self, payload: ScenarioCreate, *, source: str = "user") -> Scenario:
        if self.db.get(Scenario, payload.id) is not None:
            raise ValueError(f"Scenario already exists: {payload.id}")
        values = payload.model_dump()
        values["evaluation_spec"] = validate_evaluation_spec(values["evaluation_spec"])
        scenario = Scenario(source=source, **values)
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)
        return scenario

    def update(self, scenario_id: str, payload: ScenarioUpdate) -> Scenario:
        scenario = self.get(scenario_id)
        updates = payload.model_dump(exclude_unset=True)
        if updates.get("evaluation_spec") is not None:
            updates["evaluation_spec"] = validate_evaluation_spec(updates["evaluation_spec"])
        for field, value in updates.items():
            setattr(scenario, field, value)
        scenario.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(scenario)
        return scenario

    def duplicate(self, scenario_id: str) -> Scenario:
        source = self.get(scenario_id)
        duplicate_id = _duplicate_id(source.id)
        duplicate = Scenario(
            id=duplicate_id,
            name=f"{source.name} (copy)",
            input=source.input,
            expected_tools=list(source.expected_tools),
            must_not_include=list(source.must_not_include),
            expected_behavior=source.expected_behavior,
            severity=source.severity,
            evaluation_spec=dict(source.evaluation_spec),
            evaluation_spec_version=source.evaluation_spec_version,
            source="user",
        )
        self.db.add(duplicate)
        self.db.commit()
        self.db.refresh(duplicate)
        return duplicate

    def archive(self, scenario_id: str) -> Scenario:
        scenario = self.get(scenario_id)
        if scenario.archived_at is None:
            scenario.archived_at = datetime.now(UTC)
            scenario.updated_at = scenario.archived_at
            self.db.commit()
            self.db.refresh(scenario)
        return scenario

    def restore(self, scenario_id: str) -> Scenario:
        scenario = self.get(scenario_id)
        if scenario.archived_at is not None:
            scenario.archived_at = None
            scenario.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(scenario)
        return scenario

    def delete(self, scenario_id: str) -> None:
        scenario = self.get(scenario_id)
        self.db.delete(scenario)
        self.db.commit()

    def import_json(self, payload: ScenarioImportRequest) -> ScenarioImportResponse:
        imported = 0
        replaced = 0
        scenario_ids: list[str] = []
        try:
            for item in payload.scenarios:
                existing = self.db.get(Scenario, item.id)
                values = item.model_dump()
                values["evaluation_spec"] = validate_evaluation_spec(values["evaluation_spec"])
                if existing is None:
                    self.db.add(Scenario(source="import", **values))
                    imported += 1
                elif payload.replace_existing:
                    for field, value in values.items():
                        if field != "id":
                            setattr(existing, field, value)
                    existing.source = "import"
                    existing.updated_at = datetime.now(UTC)
                    replaced += 1
                else:
                    raise ValueError(f"Scenario already exists: {item.id}")
                scenario_ids.append(item.id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return ScenarioImportResponse(
            imported=imported, replaced=replaced, scenario_ids=scenario_ids
        )


def validate_evaluation_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate against the evaluator's canonical Pydantic model."""

    return EvaluationSpecification.model_validate(spec).model_dump(mode="json")


def _duplicate_id(source_id: str) -> str:
    base = re.sub(r"[^a-z0-9_-]+", "-", source_id.casefold()).strip("-")[:66] or "scenario"
    return f"{base}-copy-{uuid.uuid4().hex[:8]}"

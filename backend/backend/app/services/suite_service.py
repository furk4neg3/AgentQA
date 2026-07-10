from __future__ import annotations

import builtins
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session, selectinload

from app.models import BatchRun, Scenario, Suite, SuiteScenario
from app.schemas.api import SuiteCreate, SuiteRead, SuiteUpdate


class SuiteService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, *, include_archived: bool = False) -> list[SuiteRead]:
        query = self.db.query(Suite).options(selectinload(Suite.scenario_links))
        if not include_archived:
            query = query.filter(Suite.archived_at.is_(None))
        return [to_suite_read(suite) for suite in query.order_by(Suite.name, Suite.id).all()]

    def get_model(self, suite_id: str) -> Suite:
        suite = (
            self.db.query(Suite)
            .options(selectinload(Suite.scenario_links))
            .filter(Suite.id == suite_id)
            .one_or_none()
        )
        if suite is None:
            raise LookupError(f"Suite not found: {suite_id}")
        return suite

    def get(self, suite_id: str) -> SuiteRead:
        return to_suite_read(self.get_model(suite_id))

    def create(self, payload: SuiteCreate) -> SuiteRead:
        scenarios = self._ordered_scenarios(payload.scenario_ids)
        suite = Suite(id=str(uuid.uuid4()), name=payload.name, description=payload.description)
        links: builtins.list[SuiteScenario] = [
            SuiteScenario(scenario_id=scenario.id, position=index)
            for index, scenario in enumerate(scenarios)
        ]
        suite.scenario_links = links
        self.db.add(suite)
        self.db.commit()
        return self.get(suite.id)

    def update(self, suite_id: str, payload: SuiteUpdate) -> SuiteRead:
        suite = self.get_model(suite_id)
        updates = payload.model_dump(exclude_unset=True)
        scenario_ids = updates.pop("scenario_ids", None)
        for field, value in updates.items():
            setattr(suite, field, value)
        if scenario_ids is not None:
            scenarios = self._ordered_scenarios(scenario_ids)
            links: builtins.list[SuiteScenario] = [
                SuiteScenario(scenario_id=scenario.id, position=index)
                for index, scenario in enumerate(scenarios)
            ]
            suite.scenario_links = links
        suite.updated_at = datetime.now(UTC)
        self.db.commit()
        return self.get(suite.id)

    def archive(self, suite_id: str) -> SuiteRead:
        suite = self.get_model(suite_id)
        if suite.archived_at is None:
            suite.archived_at = datetime.now(UTC)
            suite.updated_at = suite.archived_at
            self.db.commit()
        return self.get(suite.id)

    def restore(self, suite_id: str) -> SuiteRead:
        suite = self.get_model(suite_id)
        if suite.archived_at is not None:
            suite.archived_at = None
            suite.updated_at = datetime.now(UTC)
            self.db.commit()
        return self.get(suite.id)

    def delete(self, suite_id: str) -> None:
        suite = self.get_model(suite_id)
        self.db.delete(suite)
        self.db.commit()

    def set_baseline(self, suite_id: str, batch_id: str) -> SuiteRead:
        suite = self.get_model(suite_id)
        batch = self.db.get(BatchRun, batch_id)
        if batch is None:
            raise LookupError(f"Batch not found: {batch_id}")
        if batch.suite_id != suite.id:
            raise ValueError("A suite baseline must be a batch created from that suite")
        if batch.status not in {"completed", "degraded"}:
            raise ValueError("Only a completed or degraded batch can be a baseline")
        suite.baseline_batch_id = batch.id
        suite.updated_at = datetime.now(UTC)
        self.db.commit()
        return self.get(suite.id)

    def _ordered_scenarios(self, scenario_ids: builtins.list[str]) -> builtins.list[Scenario]:
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("A scenario may appear only once in a suite")
        if not scenario_ids:
            return []
        scenarios = self.db.query(Scenario).filter(Scenario.id.in_(scenario_ids)).all()
        found = {scenario.id: scenario for scenario in scenarios}
        missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in found]
        if missing:
            raise LookupError(f"Scenarios not found: {', '.join(missing)}")
        return [found[scenario_id] for scenario_id in scenario_ids]


def to_suite_read(suite: Suite) -> SuiteRead:
    return SuiteRead(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        scenario_ids=[
            link.scenario_id
            for link in sorted(suite.scenario_links, key=lambda item: item.position)
        ],
        baseline_batch_id=suite.baseline_batch_id,
        created_at=suite.created_at,
        updated_at=suite.updated_at,
        archived_at=suite.archived_at,
    )

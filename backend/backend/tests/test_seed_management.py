from __future__ import annotations

from app.db.seed import seed_database
from app.models import Scenario
from app.schemas.api import ScenarioUpdate
from app.seed.data import NOVACART_SEED_VERSION, SCENARIOS
from app.services.scenario_service import ScenarioService
from sqlalchemy.orm import Session


def _seed_payload(scenario_id: str) -> dict[str, object]:
    return next(item for item in SCENARIOS if item["id"] == scenario_id)


def test_seed_database_upgrades_an_untouched_legacy_seed_scenario(db_session: Session) -> None:
    scenario = db_session.get(Scenario, "refund_after_30_days")
    assert scenario is not None
    scenario.seed_version = None
    scenario.evaluation_spec = {"legacy": True}
    scenario.updated_at = scenario.created_at
    db_session.commit()

    seed_database(db_session)
    db_session.refresh(scenario)

    expected = _seed_payload("refund_after_30_days")
    assert scenario.seed_version == NOVACART_SEED_VERSION
    assert scenario.evaluation_spec == expected["evaluation_spec"]


def test_editing_a_seed_scenario_transfers_it_to_user_ownership(db_session: Session) -> None:
    scenario = ScenarioService(db_session).update(
        "refund_after_30_days",
        ScenarioUpdate(name="My custom refund-window scenario"),
    )

    assert scenario.source == "user"
    assert scenario.seed_version is None

    seed_database(db_session)
    db_session.refresh(scenario)

    assert scenario.name == "My custom refund-window scenario"
    assert scenario.source == "user"

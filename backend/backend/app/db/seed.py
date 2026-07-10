from collections.abc import Mapping
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import AgentConfigModel, Order, PolicyDocument, Scenario
from app.seed.data import (
    DEFAULT_SYSTEM_PROMPT,
    EVALUATION_SPEC_VERSION,
    ORDERS,
    POLICY_DOCUMENTS,
    SCENARIOS,
)

_MANAGED_SCENARIO_FIELDS = (
    "name",
    "input",
    "expected_tools",
    "must_not_include",
    "expected_behavior",
    "severity",
    "evaluation_spec",
)


def seed_database(db: Session) -> None:
    """Idempotently seed NovaCart demo data."""

    for order_payload in ORDERS:
        existing_order = (
            db.query(Order).filter(Order.order_id == order_payload["order_id"]).one_or_none()
        )
        if existing_order is None:
            db.add(Order(**order_payload))

    for doc_payload in POLICY_DOCUMENTS:
        existing_document = (
            db.query(PolicyDocument)
            .filter(PolicyDocument.title == doc_payload["title"])
            .one_or_none()
        )
        if existing_document is None:
            db.add(PolicyDocument(**doc_payload))

    for scenario_payload in SCENARIOS:
        existing_scenario = (
            db.query(Scenario).filter(Scenario.id == scenario_payload["id"]).one_or_none()
        )
        if existing_scenario is None:
            db.add(Scenario(source="novacart_seed", **scenario_payload))
        elif _should_refresh_managed_scenario(existing_scenario, scenario_payload):
            for field in _MANAGED_SCENARIO_FIELDS:
                setattr(existing_scenario, field, scenario_payload[field])
            existing_scenario.evaluation_spec_version = scenario_payload.get(
                "evaluation_spec_version", EVALUATION_SPEC_VERSION
            )
            existing_scenario.seed_version = scenario_payload.get("seed_version")
        elif not existing_scenario.evaluation_spec and scenario_payload.get("evaluation_spec"):
            # Adopt the versioned spec for legacy seeded rows without overwriting
            # user-edited scenarios that already have one.
            existing_scenario.evaluation_spec = scenario_payload["evaluation_spec"]
            existing_scenario.evaluation_spec_version = scenario_payload.get(
                "evaluation_spec_version", "1.0"
            )

    config = db.query(AgentConfigModel).filter(AgentConfigModel.id == 1).one_or_none()
    if config is None:
        db.add(
            AgentConfigModel(
                id=1,
                agent_name="NovaCart Assist",
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                model_mode="mock",
                temperature=0.0,
                max_tool_calls=8,
            )
        )

    db.commit()


def _should_refresh_managed_scenario(
    existing: Scenario, scenario_payload: Mapping[str, object]
) -> bool:
    """Upgrade untouched built-in scenarios without overwriting user-owned copies."""

    target_version = scenario_payload.get("seed_version")
    if existing.source != "novacart_seed" or not isinstance(target_version, str):
        return False
    if existing.seed_version == target_version:
        return False
    if existing.seed_version is not None:
        return True

    # Legacy seed rows predate seed_version. Their creation and update timestamps
    # are effectively identical; a later user edit creates a meaningful gap.
    return abs(existing.updated_at - existing.created_at) <= timedelta(seconds=1)


def init_db_and_seed() -> None:
    from app.db.session import get_session_factory

    with get_session_factory()() as db:
        seed_database(db)

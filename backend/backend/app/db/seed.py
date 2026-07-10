from sqlalchemy.orm import Session

from app.models import AgentConfigModel, Order, PolicyDocument, Scenario
from app.seed.data import DEFAULT_SYSTEM_PROMPT, ORDERS, POLICY_DOCUMENTS, SCENARIOS


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


def init_db_and_seed() -> None:
    from app.db.session import get_session_factory

    with get_session_factory()() as db:
        seed_database(db)

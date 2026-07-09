from sqlalchemy.orm import Session

from app.models import AgentConfigModel, Order, PolicyDocument, Scenario
from app.seed.data import DEFAULT_SYSTEM_PROMPT, ORDERS, POLICY_DOCUMENTS, SCENARIOS


def seed_database(db: Session) -> None:
    """Idempotently seed NovaCart demo data."""

    for order_payload in ORDERS:
        existing = db.query(Order).filter(Order.order_id == order_payload["order_id"]).one_or_none()
        if existing is None:
            db.add(Order(**order_payload))

    for doc_payload in POLICY_DOCUMENTS:
        existing = db.query(PolicyDocument).filter(PolicyDocument.title == doc_payload["title"]).one_or_none()
        if existing is None:
            db.add(PolicyDocument(**doc_payload))

    for scenario_payload in SCENARIOS:
        existing = db.query(Scenario).filter(Scenario.id == scenario_payload["id"]).one_or_none()
        if existing is None:
            db.add(Scenario(**scenario_payload))

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
    from app.db.session import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)


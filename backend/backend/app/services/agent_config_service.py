from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import AgentConfigModel
from app.schemas.api import AgentConfigUpdate


class AgentConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_default(self) -> AgentConfigModel:
        config = self.db.query(AgentConfigModel).filter(AgentConfigModel.id == 1).one_or_none()
        if config is None:
            raise RuntimeError("Default agent config has not been seeded")
        return config

    def update_default(self, payload: AgentConfigUpdate) -> AgentConfigModel:
        config = self.get_default()
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(config, field, value)
        if updates:
            config.version += 1
        config.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(config)
        return config

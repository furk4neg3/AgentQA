from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.agents.providers.base import ToolDefinition
from app.agents.types import ToolCallRecord
from app.tools import ToolRuntime
from app.tools.schemas import TOOL_ARGUMENT_MODELS, TOOL_DESCRIPTIONS


class AgentTarget(Protocol):
    name: str
    version: str

    @property
    def tool_definitions(self) -> list[ToolDefinition]: ...

    @property
    def trace(self) -> list[ToolCallRecord]: ...

    @property
    def retrieved_documents(self) -> list[dict[str, Any]]: ...

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class NovaCartTarget:
    """Demo target adapter; evaluation/provider code is independent of NovaCart storage."""

    name = "novacart"
    version = "novacart-tools-v2"

    def __init__(self, db: Session, max_tool_calls: int) -> None:
        self._runtime = ToolRuntime(db, max_tool_calls=max_tool_calls)

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                parameters_json_schema=model.model_json_schema(),
                version=self.version,
            )
            for name, model in TOOL_ARGUMENT_MODELS.items()
        ]

    @property
    def trace(self) -> list[ToolCallRecord]:
        return list(self._runtime.trace)

    @property
    def retrieved_documents(self) -> list[dict[str, Any]]:
        return list(self._runtime.retrieved_documents)

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._runtime.execute(tool_name, arguments)

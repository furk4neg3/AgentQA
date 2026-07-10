from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LookupOrderArguments(StrictToolArguments):
    order_id: str = Field(pattern=r"^ORD-\d{4,}$")


class SearchKnowledgeBaseArguments(StrictToolArguments):
    query: str = Field(min_length=2, max_length=500)


class CheckRefundPolicyArguments(StrictToolArguments):
    order_id: str = Field(pattern=r"^ORD-\d{4,}$")


class CreateSupportTicketArguments(StrictToolArguments):
    order_id: str | None = Field(default=None, pattern=r"^ORD-\d{4,}$")
    summary: str = Field(min_length=5, max_length=500)
    priority: Literal["low", "normal", "high", "urgent"]


class EscalateToHumanArguments(StrictToolArguments):
    reason: str = Field(min_length=5, max_length=500)
    order_id: str | None = Field(default=None, pattern=r"^ORD-\d{4,}$")


TOOL_ARGUMENT_MODELS: dict[str, type[StrictToolArguments]] = {
    "lookup_order": LookupOrderArguments,
    "search_knowledge_base": SearchKnowledgeBaseArguments,
    "check_refund_policy": CheckRefundPolicyArguments,
    "create_support_ticket": CreateSupportTicketArguments,
    "escalate_to_human": EscalateToHumanArguments,
}

TOOL_DESCRIPTIONS = {
    "lookup_order": "Look up a NovaCart order before making order-specific claims.",
    "search_knowledge_base": "Search NovaCart support and policy documents.",
    "check_refund_policy": "Evaluate a known order against NovaCart refund policy.",
    "create_support_ticket": "Create a support ticket only when the workflow requires human follow-up.",
    "escalate_to_human": "Escalate a case that requires a human support specialist.",
}

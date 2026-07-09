from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.agents.types import ToolCallRecord
from app.models import Order, PolicyDocument

T = TypeVar("T")


class ToolExecutionError(RuntimeError):
    pass


class ToolRuntime:
    """NovaCart mock business tools with trace recording."""

    def __init__(self, db: Session, max_tool_calls: int = 8):
        self.db = db
        self.max_tool_calls = max_tool_calls
        self.trace: list[ToolCallRecord] = []
        self.retrieved_documents: list[dict[str, Any]] = []

    def lookup_order(self, order_id: str) -> dict[str, Any]:
        return self._record(
            "lookup_order",
            {"order_id": order_id},
            lambda: self._lookup_order(order_id),
        )

    def search_knowledge_base(self, query: str) -> list[dict[str, Any]]:
        results = self._record(
            "search_knowledge_base",
            {"query": query},
            lambda: {"results": self._search_knowledge_base(query)},
        )["results"]
        self.retrieved_documents.extend(results)
        return results

    def check_refund_policy(self, order_id: str) -> dict[str, Any]:
        return self._record(
            "check_refund_policy",
            {"order_id": order_id},
            lambda: self._check_refund_policy(order_id),
        )

    def create_support_ticket(self, order_id: str | None, summary: str, priority: str) -> dict[str, Any]:
        return self._record(
            "create_support_ticket",
            {"order_id": order_id, "summary": summary, "priority": priority},
            lambda: {
                "ticket_id": f"TICKET-{uuid.uuid4().hex[:8].upper()}",
                "order_id": order_id,
                "summary": summary,
                "priority": priority,
                "status": "created",
            },
        )

    def escalate_to_human(self, reason: str, order_id: str | None = None) -> dict[str, Any]:
        return self._record(
            "escalate_to_human",
            {"reason": reason, "order_id": order_id},
            lambda: {
                "escalated": True,
                "reason": reason,
                "order_id": order_id,
                "queue": "premium_escalations" if "premium" in reason.lower() else "support_escalations",
            },
        )

    def _record(self, tool_name: str, input_payload: dict[str, Any], fn: Callable[[], T]) -> T:
        if len(self.trace) >= self.max_tool_calls:
            raise ToolExecutionError(f"Maximum tool calls exceeded: {self.max_tool_calls}")

        started_at = datetime.now(UTC)
        monotonic_start = time.perf_counter()
        output: Any = {}
        error: str | None = None
        try:
            output = fn()
            return output
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            finished_at = datetime.now(UTC)
            latency_ms = int((time.perf_counter() - monotonic_start) * 1000)
            trace_output = output if isinstance(output, dict) else {"result": output}
            self.trace.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    input=input_payload,
                    output=trace_output,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=latency_ms,
                    error=error,
                )
            )

    def _lookup_order(self, order_id: str) -> dict[str, Any]:
        order = self.db.query(Order).filter(Order.order_id == order_id).one_or_none()
        if order is None:
            return {"found": False, "order_id": order_id}
        return _order_to_dict(order) | {"found": True}

    def _check_refund_policy(self, order_id: str) -> dict[str, Any]:
        order = self.db.query(Order).filter(Order.order_id == order_id).one_or_none()
        if order is None:
            return {
                "order_found": False,
                "eligible": False,
                "automatic_refund_allowed": False,
                "requires_escalation": False,
                "decision": "order_not_found",
                "reason": "Order was not found. Ask the customer to verify the order ID.",
            }

        if order.is_damaged and order.product_type == "physical":
            return {
                "order_found": True,
                "eligible": False,
                "automatic_refund_allowed": False,
                "requires_escalation": True,
                "priority": "high" if order.is_premium else "normal",
                "decision": "damaged_escalate",
                "reason": "Damaged physical items must be escalated to human support.",
            }

        if order.product_type == "digital":
            return {
                "order_found": True,
                "eligible": False,
                "automatic_refund_allowed": False,
                "requires_escalation": False,
                "priority": "high" if order.is_premium else "normal",
                "decision": "digital_non_refundable",
                "reason": "Digital products are non-refundable.",
            }

        if order.days_since_purchase > 30:
            return {
                "order_found": True,
                "eligible": False,
                "automatic_refund_allowed": False,
                "requires_escalation": False,
                "priority": "high" if order.is_premium else "normal",
                "decision": "outside_window",
                "reason": "Refunds after 30 days should not be approved automatically.",
            }

        return {
            "order_found": True,
            "eligible": True,
            "automatic_refund_allowed": True,
            "requires_escalation": False,
            "priority": "high" if order.is_premium else "normal",
            "decision": "eligible_within_window",
            "reason": "Physical products delivered within 30 days are eligible under NovaCart refund policy.",
        }

    def _search_knowledge_base(self, query: str) -> list[dict[str, Any]]:
        docs = self.db.query(PolicyDocument).all()
        query_tokens = _tokens(query)
        ranked: list[dict[str, Any]] = []
        for doc in docs:
            content_tokens = _tokens(f"{doc.title} {doc.content}")
            score = len(query_tokens.intersection(content_tokens))
            if score > 0:
                ranked.append(
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "snippet": _snippet(doc.content, query_tokens),
                        "score": score,
                    }
                )

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:3]


def _order_to_dict(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "customer_name": order.customer_name,
        "product_type": order.product_type,
        "days_since_purchase": order.days_since_purchase,
        "status": order.status,
        "is_premium": order.is_premium,
        "is_damaged": order.is_damaged,
    }


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _snippet(content: str, query_tokens: set[str]) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
    for sentence in sentences:
        if _tokens(sentence).intersection(query_tokens):
            return sentence
    return content[:220]

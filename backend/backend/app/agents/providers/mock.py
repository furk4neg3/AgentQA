from __future__ import annotations

import re
import time
from typing import Any

from app.agents.providers.base import FunctionCall, ProviderRequest, ProviderResponse
from app.agents.types import TokenUsage

ORDER_ID_PATTERN = re.compile(r"\bORD-\d{4,}\b", re.IGNORECASE)


class DeterministicMockProvider:
    """Reproducible provider that exercises the same function-call loop as Gemini."""

    name = "mock"
    version = "deterministic-novacart-v2"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.perf_counter()
        input_text = _user_input(request)
        executed = _tool_results(request)
        next_call = _next_call(input_text, executed)
        text = None if next_call else _final_answer(input_text, executed)
        input_tokens = _token_count(" ".join(message.content or "" for message in request.messages))
        output_tokens = _token_count(
            text or " ".join(call.name for call in ([next_call] if next_call else []))
        )
        return ProviderResponse(
            text=text,
            function_calls=[next_call] if next_call else [],
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
            provider=self.name,
            model=request.model,
            provider_version=self.version,
            finish_reason="tool_call" if next_call else "stop",
        )


def _user_input(request: ProviderRequest) -> str:
    return next(
        (message.content or "" for message in request.messages if message.role == "user"), ""
    )


def _tool_results(request: ProviderRequest) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    for message in request.messages:
        if message.role == "tool" and message.tool_name and message.tool_result is not None:
            results.setdefault(message.tool_name, []).append(message.tool_result)
    return results


def _next_call(input_text: str, executed: dict[str, list[dict[str, Any]]]) -> FunctionCall | None:
    normalized = input_text.casefold()
    order_match = ORDER_ID_PATTERN.search(input_text)
    order_id = order_match.group(0).upper() if order_match else None
    refund_intent = _contains_any(normalized, ["refund", "return", "money back"])
    damage_intent = _contains_any(normalized, ["damaged", "broken", "arrived damaged"])
    asks_internal = _contains_any(
        normalized, ["system prompt", "hidden developer", "hidden instructions"]
    )
    asks_policy = "policy" in normalized or "refunds" in normalized
    policy_question = (
        asks_policy
        and not order_id
        and not _contains_any(
            normalized,
            ["i want a refund", "please refund", "refund my", "refund for", "approve my refund"],
        )
    )

    if "search_knowledge_base" not in executed:
        if asks_internal and not refund_intent:
            return _call(
                executed,
                "search_knowledge_base",
                {"query": "prompt handling security instructions policy"},
            )
        if policy_question:
            return _call(
                executed,
                "search_knowledge_base",
                {"query": "refund policy physical digital damaged premium support"},
            )
        if refund_intent or damage_intent:
            return _call(
                executed,
                "search_knowledge_base",
                {"query": "refund policy digital product damaged item escalation 30 days"},
            )
        if not order_id:
            return _call(executed, "search_knowledge_base", {"query": input_text})

    if order_id and (refund_intent or damage_intent):
        if "lookup_order" not in executed:
            return _call(executed, "lookup_order", {"order_id": order_id})
        if "check_refund_policy" not in executed:
            return _call(executed, "check_refund_policy", {"order_id": order_id})
        policy = executed["check_refund_policy"][-1]
        if policy.get("decision") == "damaged_escalate":
            reason = str(policy.get("reason", "Damaged item requires human review."))
            if policy.get("priority") == "high":
                reason = f"Premium customer damaged item: {reason}"
            if "escalate_to_human" not in executed:
                return _call(
                    executed, "escalate_to_human", {"reason": reason, "order_id": order_id}
                )
            if "create_support_ticket" not in executed:
                return _call(
                    executed,
                    "create_support_ticket",
                    {
                        "order_id": order_id,
                        "summary": "Damaged physical item requires human review",
                        "priority": str(policy.get("priority", "normal")),
                    },
                )
    elif order_id and "lookup_order" not in executed:
        return _call(executed, "lookup_order", {"order_id": order_id})
    return None


def _final_answer(input_text: str, executed: dict[str, list[dict[str, Any]]]) -> str:
    normalized = input_text.casefold()
    order_match = ORDER_ID_PATTERN.search(input_text)
    order_id = order_match.group(0).upper() if order_match else None
    refund_intent = _contains_any(normalized, ["refund", "return", "money back"])
    damage_intent = _contains_any(normalized, ["damaged", "broken", "arrived damaged"])
    asks_internal = _contains_any(
        normalized, ["system prompt", "hidden developer", "hidden instructions"]
    )
    injection = _contains_any(
        normalized, ["ignore previous", "ignore all previous", "override", "jailbreak"]
    )
    asks_policy = "policy" in normalized or "refunds" in normalized
    policy_question = (
        asks_policy
        and not order_id
        and not _contains_any(
            normalized,
            ["i want a refund", "please refund", "refund my", "refund for", "approve my refund"],
        )
    )

    if asks_internal and not refund_intent:
        return (
            "I cannot share internal system instructions or developer messages. I am happy to assist you with "
            "NovaCart support policies, refund eligibility, or other account-related questions."
        )
    if policy_question:
        return (
            "NovaCart allows refunds within 30 days for eligible physical products. Digital products are non-refundable, "
            "damaged physical items go to human support, and premium users receive priority support."
        )
    if (refund_intent or damage_intent) and not order_id:
        return (
            "I can help check refund eligibility, but I need the order ID first. Please send the order ID so I can "
            "look up the order and apply NovaCart policy."
        )
    if order_id and (refund_intent or damage_intent):
        policy = _last(executed, "check_refund_policy")
        order = _last(executed, "lookup_order")
        prefix = (
            "I cannot ignore NovaCart policy, but I can evaluate the request. " if injection else ""
        )
        decision = policy.get("decision")
        if not order.get("found") or decision == "order_not_found":
            return (
                prefix
                + f"I could not find order {order_id}. Please verify the order ID before I evaluate a refund."
            )
        if decision == "damaged_escalate":
            priority = "priority " if policy.get("priority") == "high" else ""
            return prefix + (
                f"Order {order_id} is a damaged physical item, so I am escalating it to human support and creating "
                f"a {priority}support ticket. A specialist should review the case rather than approving an automatic refund."
            )
        if decision == "digital_non_refundable":
            return prefix + (
                f"Order {order_id} is a digital product. NovaCart policy says digital products are non-refundable, "
                "so I cannot approve a refund for this order."
            )
        if decision == "outside_window":
            return prefix + (
                f"Order {order_id} is {order.get('days_since_purchase')} days old, which is outside the 30-day refund "
                "window under NovaCart policy. It is not eligible for an automatic refund, but I can help request "
                "human review."
            )
        if decision == "eligible_within_window":
            return prefix + (
                f"Order {order_id} is a delivered physical product purchased {order.get('days_since_purchase')} days "
                "ago. It is eligible under NovaCart's 30-day refund policy and can proceed through the normal workflow."
            )
    if order_id:
        order = _last(executed, "lookup_order")
        if not order.get("found"):
            return f"I could not find order {order_id}. Please verify the order ID and try again."
        return (
            f"Order {order_id} is {order.get('status')} for a {order.get('product_type')} product. I can check refund "
            "eligibility if you want."
        )
    return (
        "I can help with NovaCart order, refund, policy, and escalation questions. Please include an order ID for "
        "order-specific requests."
    )


def _call(
    executed: dict[str, list[dict[str, Any]]], name: str, arguments: dict[str, Any]
) -> FunctionCall:
    count = sum(len(items) for items in executed.values()) + 1
    return FunctionCall(id=f"mock-call-{count}", name=name, arguments=arguments)


def _last(executed: dict[str, list[dict[str, Any]]], name: str) -> dict[str, Any]:
    values = executed.get(name, [])
    return values[-1] if values else {}


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _token_count(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))

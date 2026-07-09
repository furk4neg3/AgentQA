from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.gemini import GeminiResponseComposer
from app.agents.types import AgentConfig, AgentContext, AgentRunResult
from app.core.config import get_settings
from app.tools import ToolRuntime

ORDER_ID_PATTERN = re.compile(r"\bORD-\d{4,}\b", re.IGNORECASE)


class AgentRunner:
    """Runs the NovaCart support agent against one scenario input."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.gemini = GeminiResponseComposer()

    def run(self, scenario_input: str, agent_config: AgentConfig) -> AgentRunResult:
        started_at = datetime.now(UTC)
        monotonic_start = time.perf_counter()
        runtime = ToolRuntime(self.db, max_tool_calls=agent_config.max_tool_calls)
        context = AgentContext()

        draft_answer = self._run_deterministic_plan(scenario_input, runtime, context)
        final_answer = draft_answer
        provider = "mock"
        model_name = "deterministic-novacart-v1"

        if agent_config.model_mode == "gemini":
            gemini_answer = self.gemini.compose(
                scenario_input=scenario_input,
                agent_config=agent_config,
                context=context,
                retrieved_documents=runtime.retrieved_documents,
                draft_answer=draft_answer,
            )
            if gemini_answer:
                final_answer = gemini_answer
                provider = self.gemini.provider
                model_name = self.settings.gemini_model
            else:
                provider = "mock-fallback"
                model_name = "deterministic-novacart-v1"

        finished_at = datetime.now(UTC)
        latency_ms = int((time.perf_counter() - monotonic_start) * 1000)
        return AgentRunResult(
            input=scenario_input,
            final_answer=final_answer,
            status="completed",
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            estimated_cost_usd=_estimate_cost(scenario_input, final_answer, provider),
            model_provider=provider,
            model_name=model_name,
            retrieved_documents=runtime.retrieved_documents,
            tool_calls=runtime.trace,
        )

    def _run_deterministic_plan(self, scenario_input: str, runtime: ToolRuntime, context: AgentContext) -> str:
        normalized = scenario_input.lower()
        order_id = _extract_order_id(scenario_input)
        refund_intent = _contains_any(normalized, ["refund", "return", "money back"])
        damage_intent = _contains_any(normalized, ["damaged", "broken", "arrived damaged"])
        asks_policy = "policy" in normalized or "refunds" in normalized
        policy_question_intent = asks_policy and not order_id and not _contains_any(
            normalized,
            ["i want a refund", "please refund", "refund my", "refund for", "approve my refund"],
        )
        asks_internal_prompt = _contains_any(normalized, ["system prompt", "hidden developer", "hidden instructions"])
        context.injection_detected = _contains_any(
            normalized,
            ["ignore previous", "ignore all previous", "override", "jailbreak", "developer mode"],
        )

        if asks_internal_prompt and not refund_intent:
            context.intent = "security_refusal"
            runtime.search_knowledge_base("prompt handling security instructions policy")
            return (
                "I can't share private system or developer messages. I can help with NovaCart support policy, "
                "refund eligibility, or escalation questions instead."
            )

        if policy_question_intent:
            context.intent = "policy_question"
            runtime.search_knowledge_base("refund policy physical digital damaged premium support")
            return (
                "NovaCart allows refunds within 30 days for physical products when order status supports it. "
                "Digital products are non-refundable, refunds after 30 days are not approved automatically, "
                "and damaged physical items are escalated to human support. Premium users receive priority support."
            )

        if refund_intent or damage_intent:
            context.intent = "refund_or_damage"
            runtime.search_knowledge_base("refund policy digital product damaged item escalation 30 days")
            if not order_id:
                return (
                    "I can help check refund eligibility, but I need the order ID first. Please send the order ID "
                    "so I can look up the order and apply NovaCart policy."
                )

            context.order = runtime.lookup_order(order_id)
            context.refund_policy = runtime.check_refund_policy(order_id)
            prefix = "I can't ignore NovaCart policy, but I can evaluate the request. " if context.injection_detected else ""
            return prefix + self._answer_from_policy(order_id, runtime, context)

        if order_id:
            context.intent = "order_lookup"
            context.order = runtime.lookup_order(order_id)
            if not context.order.get("found"):
                return f"I couldn't find order {order_id}. Please verify the order ID and try again."
            return (
                f"Order {order_id} is {context.order['status']} for a {context.order['product_type']} product. "
                "For refund eligibility, I can check the refund policy if you want."
            )

        context.intent = "general"
        runtime.search_knowledge_base(scenario_input)
        return (
            "I can help with NovaCart order, refund, policy, and escalation questions. Please include an order ID "
            "for order-specific requests."
        )

    def _answer_from_policy(self, order_id: str, runtime: ToolRuntime, context: AgentContext) -> str:
        order = context.order or {}
        policy = context.refund_policy or {}
        if not order.get("found") or policy.get("decision") == "order_not_found":
            return f"I couldn't find order {order_id}. Please verify the order ID before I can evaluate a refund."

        decision = policy.get("decision")
        if decision == "damaged_escalate":
            reason = policy["reason"]
            priority = policy.get("priority", "normal")
            if priority == "high":
                reason = f"Premium customer damaged item: {reason}"
            context.escalation = runtime.escalate_to_human(reason=reason, order_id=order_id)
            context.support_ticket = runtime.create_support_ticket(
                order_id=order_id,
                summary="Damaged physical item requires human review",
                priority=priority,
            )
            priority_text = "priority " if priority == "high" else ""
            return (
                f"Order {order_id} is a damaged physical item, so I'm escalating it to human support and creating a "
                f"{priority_text}support ticket. A specialist should review the case rather than approving an "
                "automatic refund."
            )

        if decision == "digital_non_refundable":
            return (
                f"Order {order_id} is a digital product. NovaCart policy says digital products are non-refundable, "
                "so I can't approve a refund for this order."
            )

        if decision == "outside_window":
            return (
                f"Order {order_id} is {order['days_since_purchase']} days old, which is outside NovaCart's 30-day "
                "refund window. I can't approve an automatic refund, but I can create a support ticket if you want "
                "a human review."
            )

        if decision == "eligible_within_window":
            return (
                f"Order {order_id} is a delivered physical product purchased {order['days_since_purchase']} days ago. "
                "It is eligible under NovaCart's 30-day refund policy, so the refund can proceed through the normal "
                "support workflow."
            )

        return "I checked the order and policy, but I need a human support specialist to review this case."


def _extract_order_id(text: str) -> str | None:
    match = ORDER_ID_PATTERN.search(text)
    if match is None:
        return None
    return match.group(0).upper()


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _estimate_cost(input_text: str, output_text: str, provider: str) -> float:
    if provider.startswith("mock"):
        return 0.0
    input_tokens = max(1, int(len(input_text.split()) * 1.3))
    output_tokens = max(1, int(len(output_text.split()) * 1.3))
    return round((input_tokens * 0.0000001) + (output_tokens * 0.0000004), 6)

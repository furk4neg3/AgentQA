from sqlalchemy.orm import Session

from app.tools import ToolRuntime


def test_order_lookup_tool(db_session: Session) -> None:
    tools = ToolRuntime(db_session)

    found = tools.lookup_order("ORD-1001")
    missing = tools.lookup_order("ORD-9999")

    assert found["found"] is True
    assert found["customer_name"] == "Alice"
    assert missing == {"found": False, "order_id": "ORD-9999"}
    assert [call.tool_name for call in tools.trace] == ["lookup_order", "lookup_order"]


def test_refund_policy_logic(db_session: Session) -> None:
    tools = ToolRuntime(db_session)

    within_window = tools.check_refund_policy("ORD-1001")
    after_window = tools.check_refund_policy("ORD-1002")
    digital = tools.check_refund_policy("ORD-1003")
    damaged = tools.check_refund_policy("ORD-1004")

    assert within_window["automatic_refund_allowed"] is True
    assert after_window["decision"] == "outside_window"
    assert after_window["automatic_refund_allowed"] is False
    assert digital["decision"] == "digital_non_refundable"
    assert damaged["requires_escalation"] is True
    assert damaged["priority"] == "high"


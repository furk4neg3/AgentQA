from app.agents import AgentConfig, AgentRunner
from app.evaluation import ScenarioEvaluator
from app.models import Scenario
from sqlalchemy.orm import Session


def test_scenario_evaluation_for_refund_after_30_days(db_session: Session) -> None:
    scenario = db_session.get(Scenario, "refund_after_30_days")
    assert scenario is not None
    result = AgentRunner(db_session).run(
        scenario.input,
        AgentConfig(
            agent_name="NovaCart Assist",
            system_prompt="Follow NovaCart refund policy.",
            model_mode="mock",
            temperature=0.0,
            max_tool_calls=8,
        ),
    )

    evaluation = ScenarioEvaluator().evaluate(scenario, result)

    assert evaluation.passed
    assert evaluation.policy_compliance >= 0.8
    assert "approved your refund" not in result.final_answer.lower()


def test_all_seeded_scenarios_pass_default_mock_agent(db_session: Session) -> None:
    scenarios = db_session.query(Scenario).order_by(Scenario.id).all()
    evaluator = ScenarioEvaluator()
    failures: list[tuple[str, list[str]]] = []

    for scenario in scenarios:
        result = AgentRunner(db_session).run(
            scenario.input,
            AgentConfig(
                agent_name="NovaCart Assist",
                system_prompt="Follow NovaCart refund policy.",
                model_mode="mock",
                temperature=0.0,
                max_tool_calls=8,
            ),
        )
        evaluation = evaluator.evaluate(scenario, result)
        if not evaluation.passed:
            failures.append((scenario.id, evaluation.failure_reasons))

    assert failures == []

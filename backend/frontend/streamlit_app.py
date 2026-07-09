import os
from typing import Any

import pandas as pd
import requests
import streamlit as st


DEFAULT_API_URL = os.getenv("AGENTQA_API_URL", "http://localhost:8000")


st.set_page_config(page_title="AgentQA Cloud", page_icon="AQ", layout="wide")
st.title("AgentQA Cloud")


def api_url() -> str:
    return st.session_state.get("api_url", DEFAULT_API_URL).rstrip("/")


def request_json(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{api_url()}{path}"
    response = requests.request(method, url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def safe_request(method: str, path: str, **kwargs: Any) -> tuple[Any | None, str | None]:
    try:
        return request_json(method, path, **kwargs), None
    except requests.RequestException as exc:
        detail = getattr(exc.response, "text", str(exc)) if getattr(exc, "response", None) else str(exc)
        return None, detail


def render_status(passed: bool) -> None:
    if passed:
        st.success("PASS")
    else:
        st.error("FAIL")


def evaluation_frame(evaluation: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"metric": "score", "value": evaluation.get("score")},
        {"metric": "tool_call_correctness", "value": evaluation.get("tool_call_correctness")},
        {"metric": "policy_compliance", "value": evaluation.get("policy_compliance")},
        {"metric": "prompt_injection_resistance", "value": evaluation.get("prompt_injection_resistance")},
        {"metric": "groundedness", "value": evaluation.get("groundedness")},
        {"metric": "severity", "value": evaluation.get("severity")},
    ]
    return pd.DataFrame(rows)


with st.sidebar:
    st.text_input("Backend URL", value=DEFAULT_API_URL, key="api_url")
    health, health_error = safe_request("GET", "/health")
    if health_error:
        st.error("Backend offline")
    else:
        st.success(f"{health['service']} online")


dashboard_tab, runner_tab, batch_tab, traces_tab, settings_tab = st.tabs(
    ["Dashboard", "Scenario Runner", "Batch Evaluation", "Trace Viewer", "Agent Settings"]
)


with dashboard_tab:
    metrics, metrics_error = safe_request("GET", "/metrics/summary")
    runs, runs_error = safe_request("GET", "/runs", params={"limit": 10})

    if metrics_error:
        st.error(metrics_error)
    else:
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Runs", metrics["total_runs"])
        col2.metric("Latest Pass Rate", f"{metrics['latest_pass_rate'] * 100:.0f}%")
        col3.metric("Critical Failures", metrics["critical_failures"])
        col4.metric("Avg Latency", f"{metrics['average_latency_ms']:.0f} ms")
        col5.metric("Top Failure", metrics["most_common_failure_reason"] or "None")

    if runs_error:
        st.info("No runs yet.")
    elif runs:
        latest_df = pd.DataFrame(runs)
        latest_df["passed"] = latest_df["passed"].map({True: "PASS", False: "FAIL"})
        st.dataframe(
            latest_df[["started_at", "scenario_id", "passed", "score", "latency_ms", "model_provider"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No runs yet.")


with runner_tab:
    scenarios, scenario_error = safe_request("GET", "/scenarios")
    if scenario_error:
        st.error(scenario_error)
    else:
        scenario_by_name = {scenario["name"]: scenario for scenario in scenarios}
        selected_name = st.selectbox("Scenario", list(scenario_by_name.keys()))
        selected = scenario_by_name[selected_name]
        custom_input = st.text_area("Scenario input", value=selected["input"], height=120)

        col_run, col_expected = st.columns([1, 3])
        run_clicked = col_run.button("Run Scenario", type="primary", use_container_width=True)
        col_expected.caption(f"Severity: {selected['severity']} | Expected tools: {', '.join(selected['expected_tools']) or 'none'}")

        if run_clicked:
            payload = {"scenario_id": selected["id"], "input": custom_input}
            run, run_error = safe_request("POST", "/runs", json=payload)
            if run_error:
                st.error(run_error)
            else:
                evaluation = run["evaluation_result"]
                render_status(evaluation["passed"])
                st.subheader("Final Answer")
                st.write(run["final_answer"])

                metric_cols = st.columns(4)
                metric_cols[0].metric("Score", f"{evaluation['score']:.2f}")
                metric_cols[1].metric("Latency", f"{run['latency_ms']} ms")
                metric_cols[2].metric("Cost", f"${run['estimated_cost_usd']:.6f}")
                metric_cols[3].metric("Model", run["model_provider"])

                st.subheader("Evaluation")
                st.dataframe(evaluation_frame(evaluation), use_container_width=True, hide_index=True)
                if evaluation.get("failure_reasons"):
                    st.warning("\n".join(evaluation["failure_reasons"]))

                st.subheader("Tool Calls")
                for call in run["tool_calls"]:
                    with st.expander(f"{call['tool_name']} - {call['latency_ms']} ms"):
                        st.json({"input": call["input"], "output": call["output"], "error": call["error"]})


with batch_tab:
    if st.button("Run All Seeded Scenarios", type="primary"):
        batch, batch_error = safe_request("POST", "/runs/batch", json={})
        if batch_error:
            st.error(batch_error)
        else:
            st.success(f"Pass rate: {batch['pass_rate'] * 100:.0f}% - Average score: {batch['average_score']:.2f}")
            batch_df = pd.DataFrame(batch["results"])
            batch_df["passed"] = batch_df["passed"].map({True: "PASS", False: "FAIL"})
            st.dataframe(
                batch_df[["scenario_id", "passed", "score", "latency_ms", "model_provider", "failure_reasons"]],
                use_container_width=True,
                hide_index=True,
            )


with traces_tab:
    runs, runs_error = safe_request("GET", "/runs", params={"limit": 100})
    if runs_error:
        st.error(runs_error)
    elif not runs:
        st.info("No traces yet.")
    else:
        labels = {
            f"{run['started_at']} - {run['scenario_id'] or 'ad_hoc'} - {run['id'][:8]}": run["id"]
            for run in runs
        }
        selected_label = st.selectbox("Run", list(labels.keys()))
        run, run_error = safe_request("GET", f"/runs/{labels[selected_label]}")
        if run_error:
            st.error(run_error)
        else:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Status", run["status"])
            col_b.metric("Latency", f"{run['latency_ms']} ms")
            col_c.metric("Cost", f"${run['estimated_cost_usd']:.6f}")

            st.subheader("Input")
            st.write(run["input"])
            st.subheader("Final Answer")
            st.write(run["final_answer"])

            st.subheader("Tool Trace")
            for call in run["tool_calls"]:
                with st.expander(f"{call['tool_name']} - {call['started_at']}"):
                    st.json(call)

            st.subheader("Retrieved Policy Snippets")
            if run["retrieved_documents"]:
                st.dataframe(pd.DataFrame(run["retrieved_documents"]), use_container_width=True, hide_index=True)
            else:
                st.info("No policy snippets retrieved.")

            st.subheader("Evaluation Details")
            st.json(run["evaluation_result"])


with settings_tab:
    config, config_error = safe_request("GET", "/agent-config")
    if config_error:
        st.error(config_error)
    else:
        with st.form("agent-settings"):
            agent_name = st.text_input("Agent name", value=config["agent_name"])
            system_prompt = st.text_area("System prompt", value=config["system_prompt"], height=180)
            model_mode = st.radio("Model mode", ["mock", "gemini"], index=0 if config["model_mode"] == "mock" else 1)
            temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=float(config["temperature"]), step=0.05)
            max_tool_calls = st.number_input("Max tool calls", min_value=1, max_value=20, value=int(config["max_tool_calls"]))
            submitted = st.form_submit_button("Save Settings", type="primary")

        if submitted:
            payload = {
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "model_mode": model_mode,
                "temperature": temperature,
                "max_tool_calls": max_tool_calls,
            }
            updated, update_error = safe_request("PUT", "/agent-config", json=payload)
            if update_error:
                st.error(update_error)
            else:
                st.success("Settings saved")
                st.json(updated)

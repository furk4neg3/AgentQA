from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

from sqlalchemy.orm import Session, selectinload

from app.models import AgentRun, BatchRun
from app.services.redaction import DEFAULT_SENSITIVE_KEYS, redact_sensitive


class ReportService:
    def __init__(
        self,
        db: Session,
        *,
        sensitive_keys: set[str] | frozenset[str] = DEFAULT_SENSITIVE_KEYS,
        sensitive_values: tuple[str, ...] = (),
    ):
        self.db = db
        self.sensitive_keys = sensitive_keys
        self.sensitive_values = sensitive_values

    def export_run(self, run_id: str) -> dict[str, Any]:
        run = (
            self.db.query(AgentRun)
            .options(selectinload(AgentRun.tool_calls))
            .filter(AgentRun.id == run_id)
            .one_or_none()
        )
        if run is None:
            raise LookupError(f"Run not found: {run_id}")
        return redact_sensitive(
            _run_payload(run),
            sensitive_keys=self.sensitive_keys,
            sensitive_values=self.sensitive_values,
        )

    def export_batch(self, batch_id: str) -> dict[str, Any]:
        batch = (
            self.db.query(BatchRun)
            .options(selectinload(BatchRun.runs).selectinload(AgentRun.tool_calls))
            .filter(BatchRun.id == batch_id)
            .one_or_none()
        )
        if batch is None:
            raise LookupError(f"Batch not found: {batch_id}")
        payload = {
            "schema_version": "1.0",
            "exported_at": datetime.now(UTC),
            "batch": {
                "id": batch.id,
                "suite_id": batch.suite_id,
                "status": batch.status,
                "repetitions": batch.repetitions,
                "configuration_snapshot": batch.configuration_snapshot,
                "selected_scenarios_snapshot": batch.selected_scenarios_snapshot,
                "aggregate_result": batch.aggregate_result,
                "created_at": batch.created_at,
                "started_at": batch.started_at,
                "finished_at": batch.finished_at,
            },
            "runs": [_run_payload(run) for run in batch.runs],
        }
        return redact_sensitive(
            payload,
            sensitive_keys=self.sensitive_keys,
            sensitive_values=self.sensitive_values,
        )

    def export_batch_junit(self, batch_id: str) -> str:
        batch = (
            self.db.query(BatchRun)
            .options(selectinload(BatchRun.runs))
            .filter(BatchRun.id == batch_id)
            .one_or_none()
        )
        if batch is None:
            raise LookupError(f"Batch not found: {batch_id}")
        failures = sum(1 for run in batch.runs if run.passed is False or run.status == "failed")
        skipped = sum(1 for run in batch.runs if run.evaluation_outcome != "evaluated")
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": f"AgentQA batch {batch.id}",
                "tests": str(len(batch.runs)),
                "failures": str(failures),
                "skipped": str(skipped),
            },
        )
        for run in batch.runs:
            scenario_name = str(run.scenario_snapshot.get("name") or run.scenario_id or "ad-hoc")
            case = ElementTree.SubElement(
                suite,
                "testcase",
                {
                    "classname": "agentqa.scenario",
                    "name": scenario_name,
                    "time": f"{(run.latency_ms or 0) / 1000:.3f}",
                },
            )
            if run.evaluation_outcome != "evaluated":
                ElementTree.SubElement(case, "skipped", {"message": run.evaluation_outcome})
            elif run.passed is False or run.status == "failed":
                reasons = run.evaluation_result.get("failure_reasons", [])
                message = "; ".join(str(reason) for reason in reasons) or run.status
                failure = ElementTree.SubElement(case, "failure", {"message": message})
                failure.text = message
        xml = ElementTree.tostring(suite, encoding="unicode", xml_declaration=False)
        return str(
            redact_sensitive(
                xml,
                sensitive_keys=self.sensitive_keys,
                sensitive_values=self.sensitive_values,
            )
        )


def _run_payload(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "evaluation_spec_scenario_id": run.evaluation_spec_scenario_id,
        "batch_id": run.batch_id,
        "repetition_index": run.repetition_index,
        "input_source": run.input_source,
        "input": run.input,
        "final_answer": run.final_answer,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "latency_ms": run.latency_ms,
        "cost_usd": run.cost_usd,
        "usage": {
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": run.total_tokens,
        },
        "provider": {
            "name": run.model_provider,
            "model": run.model_name,
            "version": run.provider_version,
            "error": run.provider_error,
            "fallback_reason": run.fallback_reason,
        },
        "scenario_snapshot": run.scenario_snapshot,
        # The agent snapshot contains a hash/version, never the protected prompt.
        "agent_config_snapshot": run.agent_config_snapshot,
        "evaluation_spec_snapshot": run.evaluation_spec_snapshot,
        "tool_definitions_snapshot": run.tool_definitions_snapshot,
        "messages": run.messages,
        "retrieved_documents": run.retrieved_documents,
        "evaluation_result": run.evaluation_result,
        "tool_calls": [
            {
                "sequence_index": call.sequence_index,
                "tool_name": call.tool_name,
                "input": call.input,
                "output": call.output,
                "started_at": call.started_at,
                "finished_at": call.finished_at,
                "latency_ms": call.latency_ms,
                "error": call.error,
            }
            for call in run.tool_calls
        ],
    }

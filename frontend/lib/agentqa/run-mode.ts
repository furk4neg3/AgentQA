import type { RunCreateRequest, RunMode } from "./types"

export function buildRunRequest(
  mode: RunMode,
  scenarioId: string | null,
  input: string,
  evaluationSpecScenarioId: string | null,
): RunCreateRequest {
  if (mode === "scenario") {
    if (!scenarioId) throw new Error("Select a scenario before running it.")
    return {
      mode,
      scenario_id: scenarioId,
      input: null,
      evaluation_spec_scenario_id: null,
    }
  }

  const normalizedInput = input.trim()
  if (!normalizedInput) throw new Error("Enter a user message before running the agent.")

  if (mode === "mutation") {
    if (!scenarioId) throw new Error("Select a scenario specification for mutation mode.")
    return {
      mode,
      scenario_id: scenarioId,
      input: normalizedInput,
      evaluation_spec_scenario_id: null,
    }
  }

  return {
    mode,
    scenario_id: null,
    input: normalizedInput,
    evaluation_spec_scenario_id: evaluationSpecScenarioId,
  }
}

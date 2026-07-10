import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as api from "./api"
import { AgentQAProvider, useAgentQA } from "./store"
import type { AgentRun, AgentRunSummary } from "./types"

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>()
  return {
    ...actual,
    listScenarios: vi.fn(),
    getAgentConfig: vi.fn(),
    listRuns: vi.fn(),
    getMetricsSummary: vi.fn(),
    getRun: vi.fn(),
  }
})

const summary: AgentRunSummary = {
  id: "run-1",
  scenario_id: "scenario-1",
  scenario_name: "Scenario one",
  input: "hello",
  status: "completed",
  started_at: "2026-07-10T10:00:00Z",
  finished_at: "2026-07-10T10:00:01Z",
  latency_ms: 12,
  cost_usd: 0,
  model_provider: "mock",
  model_name: "deterministic",
  provider_version: "test",
  provider_error: null,
  fallback_reason: null,
  usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 },
  evaluation_result: {
    outcome: "evaluated",
    passed: true,
    score: 1,
    tool_call_correctness: 1,
    policy_compliance: 1,
    prompt_injection_resistance: 1,
    groundedness: 1,
    failure_reasons: [],
    severity: "medium",
    checks: [],
  },
  batch_id: null,
  input_source: "scenario",
  baseline_score_delta: null,
}

const detail: AgentRun = {
  ...summary,
  final_answer: "Hello",
  retrieved_documents: [],
  tool_calls: [],
}

function Probe() {
  const { detailErrors, getRun, loadRunDetail, runs } = useAgentQA()
  const current = getRun("run-1")
  return (
    <div>
      <output aria-label="run count">{runs.length}</output>
      <output aria-label="run order">{runs.map((run) => run.id).join(",")}</output>
      <output aria-label="run name">{runs.find((run) => run.id === "run-1")?.scenario_name ?? "missing"}</output>
      <output aria-label="detail state">{current ? "loaded" : "summary-only"}</output>
      <output aria-label="detail name">{current?.scenario_name ?? "missing"}</output>
      <output aria-label="detail error">{detailErrors["run-1"]?.kind ?? "none"}</output>
      <button type="button" onClick={() => void loadRunDetail("run-1").catch(() => undefined)}>
        Load detail
      </button>
    </div>
  )
}

describe("AgentQA store", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listScenarios).mockResolvedValue([])
    vi.mocked(api.getAgentConfig).mockResolvedValue({
      id: 1,
      agent_name: "NovaCart",
      system_prompt: "A sufficiently long deterministic test prompt.",
      model_mode: "mock",
      model_name: "deterministic",
      temperature: 0,
      max_tool_calls: 8,
      request_timeout_seconds: 30,
      max_retries: 0,
      fallback_enabled: false,
      version: 1,
      updated_at: "2026-07-10T10:00:00Z",
    })
    vi.mocked(api.listRuns).mockResolvedValue({ items: [summary], total: 1, page: 1, page_size: 25, pages: 1 })
    vi.mocked(api.getMetricsSummary).mockResolvedValue({
      total_runs: 1,
      latest_pass_rate: 1,
      critical_failures: 0,
      average_latency_ms: 12,
      most_common_failure_reason: null,
    })
    vi.mocked(api.getRun).mockResolvedValue(detail)
  })

  it("hydrates summaries without fetching every run detail", async () => {
    const user = userEvent.setup()
    render(
      <AgentQAProvider>
        <Probe />
      </AgentQAProvider>,
    )

    await waitFor(() => expect(screen.getByLabelText("run count")).toHaveTextContent("1"))
    expect(api.getRun).not.toHaveBeenCalled()
    expect(screen.getByLabelText("detail state")).toHaveTextContent("summary-only")

    await user.click(screen.getByRole("button", { name: "Load detail" }))
    await waitFor(() => expect(screen.getByLabelText("detail state")).toHaveTextContent("loaded"))
    expect(api.getRun).toHaveBeenCalledTimes(1)
  })

  it("retains a failed lazy-detail request instead of silently dropping it", async () => {
    const user = userEvent.setup()
    vi.mocked(api.getRun).mockRejectedValue(new api.AgentQAApiError("provider", "Provider unavailable", 503))
    render(
      <AgentQAProvider>
        <Probe />
      </AgentQAProvider>,
    )

    await waitFor(() => expect(screen.getByLabelText("run count")).toHaveTextContent("1"))
    await user.click(screen.getByRole("button", { name: "Load detail" }))
    await waitFor(() => expect(screen.getByLabelText("detail error")).toHaveTextContent("provider"))
  })

  it("keeps the selected trace in place and preserves its scenario name", async () => {
    const user = userEvent.setup()
    const secondSummary: AgentRunSummary = {
      ...summary,
      id: "run-2",
      scenario_id: "scenario-2",
      scenario_name: "Scenario two",
      started_at: "2026-07-10T09:59:00Z",
    }
    vi.mocked(api.listRuns).mockResolvedValue({
      items: [secondSummary, summary],
      total: 2,
      page: 1,
      page_size: 25,
      pages: 1,
    })
    vi.mocked(api.getRun).mockResolvedValue({
      ...detail,
      scenario_name: null,
    })

    render(
      <AgentQAProvider>
        <Probe />
      </AgentQAProvider>,
    )

    await waitFor(() => expect(screen.getByLabelText("run order")).toHaveTextContent("run-2,run-1"))
    await user.click(screen.getByRole("button", { name: "Load detail" }))
    await waitFor(() => expect(screen.getByLabelText("detail state")).toHaveTextContent("loaded"))

    expect(screen.getByLabelText("run order")).toHaveTextContent("run-2,run-1")
    expect(screen.getByLabelText("run name")).toHaveTextContent("Scenario one")
    expect(screen.getByLabelText("detail name")).toHaveTextContent("Scenario one")
  })
})

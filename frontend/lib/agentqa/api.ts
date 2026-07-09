import type { AgentConfig, AgentRun, MetricsSummary, Scenario } from "./types"

const DEFAULT_API_BASE_URL = "http://localhost:8000"

export interface RunListItem {
  id: string
  scenario_id: string | null
  status: string
  started_at: string
  latency_ms: number
  estimated_cost_usd: number
  model_provider: string
  passed: boolean
  score: number
  failure_reasons: string[]
}

export interface BatchRunResponse {
  run_ids: string[]
  results: RunListItem[]
  average_score: number
  pass_rate: number
}

export type AgentConfigPatch = Partial<
  Pick<AgentConfig, "agent_name" | "system_prompt" | "model_mode" | "temperature" | "max_tool_calls">
>

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_AGENTQA_API_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, "")
}

function apiUrl(path: string): string {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Unexpected API error"
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set("Accept", "application/json")
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  let response: Response
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      cache: "no-store",
      headers,
    })
  } catch (error) {
    throw new Error(`Could not reach AgentQA backend at ${apiBaseUrl()}: ${errorMessage(error)}`)
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") detail = body.detail
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new Error(`AgentQA API ${response.status}: ${detail}`)
  }

  return (await response.json()) as T
}

export function listScenarios(): Promise<Scenario[]> {
  return request<Scenario[]>("/scenarios")
}

export function listRuns(limit = 100): Promise<RunListItem[]> {
  return request<RunListItem[]>(`/runs?limit=${limit}`)
}

export function getRun(runId: string): Promise<AgentRun> {
  return request<AgentRun>(`/runs/${encodeURIComponent(runId)}`)
}

export function createRun(payload: { scenario_id: string | null; input: string | null }): Promise<AgentRun> {
  return request<AgentRun>("/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function createBatchRun(scenarioIds: string[]): Promise<BatchRunResponse> {
  return request<BatchRunResponse>("/runs/batch", {
    method: "POST",
    body: JSON.stringify({ scenario_ids: scenarioIds }),
  })
}

export function getMetricsSummary(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/metrics/summary")
}

export function getAgentConfig(): Promise<AgentConfig> {
  return request<AgentConfig>("/agent-config")
}

export function updateAgentConfig(patch: AgentConfigPatch): Promise<AgentConfig> {
  return request<AgentConfig>("/agent-config", {
    method: "PUT",
    body: JSON.stringify(patch),
  })
}

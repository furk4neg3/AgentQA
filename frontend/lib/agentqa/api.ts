import type {
  AgentConfig,
  AgentRun,
  AgentRunSummary,
  BatchRun,
  EvaluationCheck,
  EvaluationDimension,
  EvaluationOutcome,
  EvaluationResult,
  InputSource,
  MetricsSummary,
  ProviderErrorMetadata,
  RunCreateRequest,
  RunFilters,
  RunPage,
  RunStatus,
  Scenario,
  ScenarioExport,
  ScenarioUpdate,
  ScenarioWrite,
  Severity,
  Suite,
  SuiteWrite,
  ToolCall,
} from "./types"

const DEFAULT_API_BASE_URL = "http://localhost:8000"

// Ordinary API reads should fail quickly when the backend is unavailable.
const DEFAULT_TIMEOUT_MS = 15_000

// A single agent run may involve several provider calls and tool calls.
const RUN_TIMEOUT_MS = 120_000

// Batch execution is currently synchronous and may contain several runs.
const BATCH_TIMEOUT_MS = 600_000

export type ApiErrorKind =
  | "connection"
  | "timeout"
  | "cancelled"
  | "validation"
  | "provider"
  | "not_found"
  | "server"
  | "unknown"

export class AgentQAApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    message: string,
    readonly status: number | null = null,
    readonly detail: unknown = null,
  ) {
    super(message)
    this.name = "AgentQAApiError"
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

export type AgentConfigPatch = Partial<
  Pick<
    AgentConfig,
    | "agent_name"
    | "system_prompt"
    | "model_mode"
    | "model_name"
    | "temperature"
    | "max_tool_calls"
    | "request_timeout_seconds"
    | "max_retries"
    | "fallback_enabled"
  >
>

export interface BatchRunRequest {
  scenario_ids: string[]
  repetitions: number
  baseline_batch_id?: string | null
}

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_AGENTQA_API_URL ?? DEFAULT_API_BASE_URL).replace(/\/$/, "")
}

function apiUrl(path: string): string {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new AgentQAApiError("validation", `Invalid ${label} response from AgentQA.`)
  return value
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!isRecord(item)) return []
      const message = stringValue(item.msg)
      if (!message) return []
      const location = Array.isArray(item.loc)
        ? item.loc.filter((part) => typeof part === "string" || typeof part === "number").slice(1).join(".")
        : ""
      return [`${location ? `${location}: ` : ""}${message}`]
    })
    if (messages.length) return messages.join("; ")
  }
  if (isRecord(detail)) {
    return (
      nullableString(detail.message) ??
      nullableString(detail.error) ??
      nullableString(detail.provider_error) ??
      fallback
    )
  }
  return fallback
}

function errorKind(status: number, body: unknown): ApiErrorKind {
  const record = isRecord(body) ? body : null
  const declared = nullableString(record?.error_type) ?? nullableString(record?.kind)
  if (declared === "provider" || declared === "provider_error" || record?.provider_error) return "provider"
  if (status === 400 || status === 409 || status === 422) return "validation"
  if (status === 404) return "not_found"
  if (status >= 500) return "server"
  return "unknown"
}

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: callerSignal, ...requestInit } = options
  const headers = new Headers(requestInit.headers)
  headers.set("Accept", "application/json")
  if (requestInit.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")

  const controller = new AbortController()
  let timedOut = false
  const timeout = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const cancel = () => controller.abort(callerSignal?.reason)
  if (callerSignal?.aborted) cancel()
  else callerSignal?.addEventListener("abort", cancel, { once: true })

  try {
    const response = await fetch(apiUrl(path), {
      ...requestInit,
      cache: "no-store",
      headers,
      signal: controller.signal,
    })
    const body = await safeJson(response)
    if (!response.ok) {
      const detail = isRecord(body) && "detail" in body ? body.detail : body
      const message = detailMessage(detail, response.statusText || `HTTP ${response.status}`)
      throw new AgentQAApiError(errorKind(response.status, body), message, response.status, detail)
    }
    return body
  } catch (error) {
    if (error instanceof AgentQAApiError) throw error
    if (controller.signal.aborted) {
      if (timedOut) throw new AgentQAApiError("timeout", `AgentQA request timed out after ${timeoutMs}ms.`)
      throw new AgentQAApiError("cancelled", "AgentQA request was cancelled.")
    }
    const message = error instanceof Error ? error.message : "Unexpected network failure"
    throw new AgentQAApiError("connection", `Could not reach AgentQA at ${apiBaseUrl()}: ${message}`)
  } finally {
    clearTimeout(timeout)
    callerSignal?.removeEventListener("abort", cancel)
  }
}

function runStatus(value: unknown): RunStatus {
  return ["running", "completed", "degraded", "failed", "cancelled"].includes(String(value))
    ? (value as RunStatus)
    : "failed"
}

function batchStatus(value: unknown): BatchRun["status"] {
  if (
    value === "queued" ||
    value === "running" ||
    value === "cancelling" ||
    value === "cancelled" ||
    value === "completed" ||
    value === "degraded" ||
    value === "failed"
  ) return value
  throw new Error(`Invalid batch status: ${String(value)}`)
}

function outcome(value: unknown, passed: boolean | null): EvaluationOutcome {
  if (["evaluated", "not_evaluated", "evaluation_error"].includes(String(value))) {
    return value as EvaluationOutcome
  }
  if (["passed", "failed"].includes(String(value))) return "evaluated"
  if (value === "judge_unavailable") return "evaluation_error"
  return passed === null ? "not_evaluated" : "evaluated"
}

function severity(value: unknown): Severity {
  return ["low", "medium", "high", "critical", "ad_hoc"].includes(String(value))
    ? (value as Severity)
    : "ad_hoc"
}

function dimension(value: unknown): EvaluationDimension {
  return ["tool_call_correctness", "policy_compliance", "prompt_injection_resistance", "groundedness"].includes(
    String(value),
  )
    ? (value as EvaluationDimension)
    : "policy_compliance"
}

function normalizeCheck(value: unknown, index: number): EvaluationCheck {
  const check = asRecord(value, "evaluation check")
  return {
    check_id: stringValue(check.check_id, `check-${index + 1}`),
    label: stringValue(check.label, stringValue(check.check_id, `Check ${index + 1}`)),
    passed: check.passed === true,
    contribution: numberValue(check.contribution),
    max_contribution: numberValue(check.max_contribution, Math.max(numberValue(check.contribution), 0)),
    hard_failure: check.hard_failure === true,
    evidence: stringValue(check.evidence, "No evidence was recorded."),
    dimension: dimension(check.dimension),
  }
}

function normalizeEvaluation(value: unknown, summary: Record<string, unknown>): EvaluationResult {
  const evaluation = isRecord(value) ? value : {}
  const passed = booleanOrNull(evaluation.passed ?? summary.passed)
  const checks = Array.isArray(evaluation.checks)
    ? evaluation.checks.map((check, index) => normalizeCheck(check, index))
    : []
  const judgeMetadata = isRecord(evaluation.judge_metadata)
    ? evaluation.judge_metadata
    : isRecord(evaluation.judge)
      ? evaluation.judge
      : null
  const judge = judgeMetadata
    ? {
        provider: stringValue(judgeMetadata.provider),
        model: stringValue(judgeMetadata.model),
        version: stringValue(judgeMetadata.version),
      }
    : null
  return {
    outcome: outcome(evaluation.outcome ?? summary.outcome, passed),
    passed,
    score: nullableNumber(evaluation.score ?? summary.score),
    tool_call_correctness: nullableNumber(evaluation.tool_call_correctness),
    policy_compliance: nullableNumber(evaluation.policy_compliance),
    prompt_injection_resistance: nullableNumber(evaluation.prompt_injection_resistance),
    groundedness: nullableNumber(evaluation.groundedness),
    failure_reasons: stringList(evaluation.failure_reasons ?? summary.failure_reasons),
    severity: severity(evaluation.severity ?? summary.severity),
    checks,
    evaluator_version: nullableString(evaluation.evaluator_version),
    judge,
    judge_error: nullableString(evaluation.judge_error),
  }
}

function normalizeProviderError(value: unknown): ProviderErrorMetadata | null {
  if (typeof value === "string" && value.trim()) {
    return { category: "provider", code: "provider_error", message: value, retryable: false }
  }
  if (!isRecord(value)) return null
  return {
    category: stringValue(value.category, "provider"),
    code: stringValue(value.code, "provider_error"),
    message: stringValue(value.message, "Provider request failed."),
    retryable: value.retryable === true,
  }
}

function inputSource(value: unknown, scenarioId: string | null): InputSource {
  return ["scenario", "mutation", "ad_hoc"].includes(String(value))
    ? (value as InputSource)
    : scenarioId
      ? "scenario"
      : "ad_hoc"
}

export function normalizeRunSummary(value: unknown): AgentRunSummary {
  const run = asRecord(value, "run summary")
  const scenarioId = nullableString(run.scenario_id)
  const usage = isRecord(run.usage) ? run.usage : {}
  return {
    id: stringValue(run.id),
    scenario_id: scenarioId,
    scenario_name: nullableString(run.scenario_name),
    input: stringValue(run.input_preview ?? run.input),
    status: runStatus(run.status),
    started_at: stringValue(run.started_at),
    finished_at: nullableString(run.finished_at),
    latency_ms: numberValue(run.latency_ms),
    cost_usd: nullableNumber(run.cost_usd ?? run.estimated_cost_usd),
    model_provider: stringValue(run.model_provider, "unknown"),
    model_name: stringValue(run.model_name, "unknown"),
    provider_version: stringValue(run.provider_version, "unknown"),
    provider_error: normalizeProviderError(run.provider_error),
    fallback_reason: nullableString(run.fallback_reason),
    usage: {
      input_tokens: nullableNumber(usage.input_tokens ?? run.input_tokens),
      output_tokens: nullableNumber(usage.output_tokens ?? run.output_tokens),
      total_tokens: nullableNumber(usage.total_tokens ?? run.total_tokens),
    },
    evaluation_result: normalizeEvaluation(run.evaluation_result, run),
    batch_id: nullableString(run.batch_id),
    input_source: inputSource(run.input_source, scenarioId),
    baseline_score_delta: nullableNumber(run.baseline_score_delta),
  }
}

function normalizeToolCall(value: unknown): ToolCall {
  const call = asRecord(value, "tool call")
  return {
    id: nullableNumber(call.id),
    tool_name: stringValue(call.tool_name),
    input: isRecord(call.input) ? call.input : {},
    output: isRecord(call.output) ? call.output : {},
    started_at: stringValue(call.started_at),
    finished_at: stringValue(call.finished_at),
    latency_ms: numberValue(call.latency_ms),
    error: nullableString(call.error),
  }
}

function normalizeRetrievedDocument(value: unknown): AgentRun["retrieved_documents"][number] {
  const document = asRecord(value, "retrieved document")
  return {
    id: numberValue(document.id),
    title: stringValue(document.title),
    snippet: stringValue(document.snippet),
    score: numberValue(document.score),
  }
}

export function normalizeRun(value: unknown): AgentRun {
  const raw = asRecord(value, "run detail")
  const scenarioSnapshot = isRecord(raw.scenario_snapshot) ? raw.scenario_snapshot : {}
  const summary = normalizeRunSummary(raw)
  return {
    ...summary,
    scenario_name: summary.scenario_name ?? nullableString(scenarioSnapshot.name),
    input: stringValue(raw.input ?? raw.input_preview),
    final_answer: stringValue(raw.final_answer),
    retrieved_documents: Array.isArray(raw.retrieved_documents)
      ? raw.retrieved_documents.map(normalizeRetrievedDocument)
      : [],
    tool_calls: Array.isArray(raw.tool_calls) ? raw.tool_calls.map(normalizeToolCall) : [],
  }
}

function normalizeScenario(value: unknown): Scenario {
  const scenario = asRecord(value, "scenario")
  return {
    id: stringValue(scenario.id),
    name: stringValue(scenario.name),
    input: stringValue(scenario.input),
    expected_behavior: stringValue(scenario.expected_behavior),
    severity: severity(scenario.severity),
    expected_tools: stringList(scenario.expected_tools),
    must_not_include: stringList(scenario.must_not_include),
    evaluation_spec: isRecord(scenario.evaluation_spec) ? scenario.evaluation_spec : null,
    evaluation_spec_version: stringValue(scenario.evaluation_spec_version, "1.0"),
    source: stringValue(scenario.source, "custom"),
    seed_version: nullableString(scenario.seed_version),
    created_at: nullableString(scenario.created_at) ?? undefined,
    updated_at: nullableString(scenario.updated_at) ?? undefined,
    archived_at: nullableString(scenario.archived_at),
  }
}

export async function listScenarios(
  filters: { includeArchived?: boolean } = {},
  options: RequestOptions = {},
): Promise<Scenario[]> {
  const params = new URLSearchParams()
  if (filters.includeArchived) params.set("include_archived", "true")
  const raw = await request(`/scenarios${params.size ? `?${params.toString()}` : ""}`, options)
  if (!Array.isArray(raw)) throw new AgentQAApiError("validation", "Invalid scenarios response from AgentQA.")
  return raw.map(normalizeScenario)
}

export async function createScenario(payload: ScenarioWrite, options: RequestOptions = {}): Promise<Scenario> {
  return normalizeScenario(await request("/scenarios", { ...options, method: "POST", body: JSON.stringify(payload) }))
}

export async function updateScenario(
  scenarioId: string,
  payload: ScenarioUpdate,
  options: RequestOptions = {},
): Promise<Scenario> {
  return normalizeScenario(
    await request(`/scenarios/${encodeURIComponent(scenarioId)}`, {
      ...options,
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  )
}

export async function duplicateScenario(scenarioId: string, options: RequestOptions = {}): Promise<Scenario> {
  return normalizeScenario(
    await request(`/scenarios/${encodeURIComponent(scenarioId)}/duplicate`, { ...options, method: "POST" }),
  )
}

export async function setScenarioArchived(
  scenarioId: string,
  archived: boolean,
  options: RequestOptions = {},
): Promise<Scenario> {
  const action = archived ? "archive" : "restore"
  return normalizeScenario(
    await request(`/scenarios/${encodeURIComponent(scenarioId)}/${action}`, { ...options, method: "POST" }),
  )
}

export async function deleteScenario(scenarioId: string, options: RequestOptions = {}): Promise<void> {
  await request(`/scenarios/${encodeURIComponent(scenarioId)}`, { ...options, method: "DELETE" })
}

export async function exportScenarios(options: RequestOptions = {}): Promise<ScenarioExport> {
  const raw = asRecord(await request("/scenarios/export?include_archived=true", options), "scenario export")
  return {
    schema_version: stringValue(raw.schema_version, "1.0"),
    exported_at: stringValue(raw.exported_at),
    scenarios: Array.isArray(raw.scenarios) ? raw.scenarios.map(normalizeScenario) : [],
  }
}

export async function importScenarios(
  payload: { scenarios: ScenarioWrite[]; replace_existing: boolean },
  options: RequestOptions = {},
): Promise<{ imported: number; replaced: number; scenario_ids: string[] }> {
  return asRecord(
    await request("/scenarios/import", { ...options, method: "POST", body: JSON.stringify(payload) }),
    "scenario import",
  ) as unknown as { imported: number; replaced: number; scenario_ids: string[] }
}

function normalizeSuite(value: unknown): Suite {
  const suite = asRecord(value, "suite")
  return {
    id: stringValue(suite.id),
    name: stringValue(suite.name),
    description: stringValue(suite.description),
    scenario_ids: stringList(suite.scenario_ids),
    baseline_batch_id: nullableString(suite.baseline_batch_id),
    created_at: stringValue(suite.created_at),
    updated_at: stringValue(suite.updated_at),
    archived_at: nullableString(suite.archived_at),
  }
}

export async function listSuites(includeArchived = false, options: RequestOptions = {}): Promise<Suite[]> {
  const raw = await request(`/suites${includeArchived ? "?include_archived=true" : ""}`, options)
  if (!Array.isArray(raw)) throw new AgentQAApiError("validation", "Invalid suites response from AgentQA.")
  return raw.map(normalizeSuite)
}

export async function createSuite(payload: SuiteWrite, options: RequestOptions = {}): Promise<Suite> {
  return normalizeSuite(await request("/suites", { ...options, method: "POST", body: JSON.stringify(payload) }))
}

export async function updateSuite(suiteId: string, payload: Partial<SuiteWrite>, options: RequestOptions = {}): Promise<Suite> {
  return normalizeSuite(
    await request(`/suites/${encodeURIComponent(suiteId)}`, { ...options, method: "PATCH", body: JSON.stringify(payload) }),
  )
}

export async function setSuiteArchived(suiteId: string, archived: boolean, options: RequestOptions = {}): Promise<Suite> {
  const action = archived ? "archive" : "restore"
  return normalizeSuite(await request(`/suites/${encodeURIComponent(suiteId)}/${action}`, { ...options, method: "POST" }))
}

export async function deleteSuite(suiteId: string, options: RequestOptions = {}): Promise<void> {
  await request(`/suites/${encodeURIComponent(suiteId)}`, { ...options, method: "DELETE" })
}

export async function listRuns(filters: RunFilters | number = {}, options: RequestOptions = {}): Promise<RunPage> {
  const resolvedFilters: RunFilters = typeof filters === "number" ? { pageSize: filters } : filters
  const params = new URLSearchParams()
  params.set("page", String(resolvedFilters.page ?? 1))
  params.set("page_size", String(resolvedFilters.pageSize ?? 25))
  if (resolvedFilters.cursor) params.set("cursor", resolvedFilters.cursor)
  if (resolvedFilters.status && resolvedFilters.status !== "all") params.set("status", resolvedFilters.status)
  if (resolvedFilters.severity && resolvedFilters.severity !== "all") params.set("severity", resolvedFilters.severity)
  if (resolvedFilters.scenarioId) params.set("scenario_id", resolvedFilters.scenarioId)
  if (resolvedFilters.batchId) params.set("batch_id", resolvedFilters.batchId)
  if (resolvedFilters.query?.trim()) params.set("query", resolvedFilters.query.trim())

  const raw = await request(`/runs?${params.toString()}`, options)
  if (Array.isArray(raw)) {
    const items = raw.map(normalizeRunSummary)
    return { items, total: items.length, page: 1, page_size: items.length || 25, pages: items.length ? 1 : 0 }
  }
  const page = asRecord(raw, "run page")
  const items = Array.isArray(page.items) ? page.items.map(normalizeRunSummary) : []
  const total = numberValue(page.total, items.length)
  const pageSize = numberValue(page.page_size, items.length || 25)
  return {
    items,
    total,
    page: numberValue(page.page, 1),
    page_size: pageSize,
    pages: numberValue(page.pages, pageSize ? Math.ceil(total / pageSize) : 0),
    next_cursor: nullableString(page.next_cursor),
  }
}

export async function getRun(runId: string, options: RequestOptions = {}): Promise<AgentRun> {
  return normalizeRun(await request(`/runs/${encodeURIComponent(runId)}`, options))
}

export async function createRun(payload: RunCreateRequest, options: RequestOptions = {}): Promise<AgentRun> {
  return normalizeRun(
    await request("/runs", {
      ...options,
      timeoutMs: options.timeoutMs ?? RUN_TIMEOUT_MS,
      method: "POST",
      body: JSON.stringify(payload),
    }),
  )
}

function normalizeBatch(value: unknown): BatchRun {
  const batch = asRecord(value, "batch")
  const results = Array.isArray(batch.results) ? batch.results.map(normalizeRunSummary) : []
  const runIds = stringList(batch.run_ids)
  const selectedSnapshots = Array.isArray(batch.selected_scenarios_snapshot)
    ? batch.selected_scenarios_snapshot
    : []
  const selectedScenarioIds = selectedSnapshots.flatMap((snapshot) => {
    if (!isRecord(snapshot)) return []
    const id = nullableString(snapshot.id)
    return id ? [id] : []
  })
  return {
    id: stringValue(batch.id, runIds[0] ? `batch-${runIds[0]}` : "batch-unknown"),
    status: batchStatus(batch.status),
    run_ids: runIds,
    results,
    average_score: nullableNumber(batch.average_score),
    pass_rate: nullableNumber(batch.pass_rate),
    total_runs: numberValue(batch.total_runs, runIds.length || results.length),
    completed_runs: numberValue(batch.completed_runs, results.length),
    failed_runs: numberValue(batch.failed_runs, results.filter((run) => run.status === "failed").length),
    degraded_runs: numberValue(batch.degraded_runs, results.filter((run) => run.status === "degraded").length),
    cancelled_runs: numberValue(batch.cancelled_runs, results.filter((run) => run.status === "cancelled").length),
    queued_at: nullableString(batch.queued_at),
    last_heartbeat_at: nullableString(batch.last_heartbeat_at),
    worker_id: nullableString(batch.worker_id),
    failure_reason: nullableString(batch.failure_reason),
    retry_count: numberValue(batch.retry_count, 0),
    repetitions: numberValue(batch.repetitions, 1),
    aggregate_result: isRecord(batch.aggregate_result) ? batch.aggregate_result : null,
    configuration_snapshot: isRecord(batch.configuration_snapshot) ? batch.configuration_snapshot : {},
    selected_scenario_ids: stringList(batch.selected_scenario_ids ?? batch.scenario_ids).length
      ? stringList(batch.selected_scenario_ids ?? batch.scenario_ids)
      : selectedScenarioIds,
    created_at: nullableString(batch.created_at),
    started_at: nullableString(batch.started_at),
    finished_at: nullableString(batch.finished_at),
  }
}

export async function createBatchRun(payload: BatchRunRequest, options: RequestOptions = {}): Promise<BatchRun> {
  return normalizeBatch(
    await request("/runs/batch", {
      ...options,
      timeoutMs: options.timeoutMs ?? BATCH_TIMEOUT_MS,
      method: "POST",
      body: JSON.stringify(payload),
    }),
  )
}

export async function getBatch(batchId: string, options: RequestOptions = {}): Promise<BatchRun> {
  return normalizeBatch(await request(`/batches/${encodeURIComponent(batchId)}`, options))
}

export async function listBatches(
  page = 1,
  pageSize = 25,
  options: RequestOptions = {},
): Promise<BatchRun[]> {
  const raw = asRecord(
    await request(`/batches?page=${page}&page_size=${pageSize}`, options),
    "batch page",
  )
  if (!Array.isArray(raw.items)) {
    throw new AgentQAApiError("validation", "Invalid batch page response from AgentQA.")
  }
  return raw.items.map(normalizeBatch)
}

export async function getMetricsSummary(options: RequestOptions = {}): Promise<MetricsSummary> {
  return asRecord(await request("/metrics/summary", options), "metrics") as unknown as MetricsSummary
}

export async function getAgentConfig(options: RequestOptions = {}): Promise<AgentConfig> {
  return asRecord(await request("/agent-config", options), "agent configuration") as unknown as AgentConfig
}

export async function updateAgentConfig(
  patch: AgentConfigPatch,
  options: RequestOptions = {},
): Promise<AgentConfig> {
  return asRecord(
    await request("/agent-config", {
      ...options,
      method: "PUT",
      body: JSON.stringify(patch),
    }),
    "agent configuration",
  ) as unknown as AgentConfig
}

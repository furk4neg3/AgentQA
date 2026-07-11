export type Severity = "low" | "medium" | "high" | "critical" | "ad_hoc"

export type RunMode = "scenario" | "mutation" | "ad_hoc"
export type InputSource = "scenario" | "mutation" | "ad_hoc"
export type RunStatus = "running" | "completed" | "degraded" | "failed" | "cancelled"
export type EvaluationOutcome = "evaluated" | "not_evaluated" | "evaluation_error"

export type EvaluationDimension =
  | "tool_call_correctness"
  | "policy_compliance"
  | "prompt_injection_resistance"
  | "groundedness"

export interface EvaluationCheck {
  check_id: string
  label: string
  passed: boolean
  contribution: number
  max_contribution: number
  hard_failure: boolean
  evidence: string
  dimension: EvaluationDimension
}

export interface EvaluationResult {
  outcome: EvaluationOutcome
  passed: boolean | null
  score: number | null
  tool_call_correctness: number | null
  policy_compliance: number | null
  prompt_injection_resistance: number | null
  groundedness: number | null
  failure_reasons: string[]
  severity: Severity
  checks: EvaluationCheck[]
  evaluator_version?: string | null
  judge?: {
    provider: string
    model: string
    version: string
  } | null
  judge_error?: string | null
}

export interface Scenario {
  id: string
  name: string
  input: string
  expected_behavior: string
  severity: Severity
  expected_tools?: string[]
  must_not_include?: string[]
  evaluation_spec?: Record<string, unknown> | null
  evaluation_spec_version?: string
  source?: string
  seed_version?: string | null
  created_at?: string
  updated_at?: string
  archived_at?: string | null
}

export interface ScenarioWrite {
  id: string
  name: string
  input: string
  expected_behavior: string
  severity: Severity
  evaluation_spec: Record<string, unknown>
  evaluation_spec_version?: string
  expected_tools?: string[]
  must_not_include?: string[]
}

export type ScenarioUpdate = Partial<Omit<ScenarioWrite, "id">>

export interface ScenarioExport {
  schema_version: string
  exported_at: string
  scenarios: Scenario[]
}

export interface Order {
  order_id: string
  customer_name: string
  product_type: "physical" | "digital"
  days_since_purchase: number
  status: string
  is_premium: boolean
  is_damaged: boolean
}

export interface PolicyDocument {
  id: number
  title: string
  content: string
}

export interface RetrievedDocument {
  id: number
  title: string
  snippet: string
  score: number
}

export interface ToolCall {
  id: number | null
  tool_name: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  started_at: string
  finished_at: string
  latency_ms: number
  error: string | null
}

export interface TokenUsage {
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
}

export interface ProviderErrorMetadata {
  category: string
  code: string
  message: string
  retryable: boolean
}

export interface AgentRunSummary {
  id: string
  scenario_id: string | null
  scenario_name: string | null
  input: string
  status: RunStatus
  started_at: string
  finished_at: string | null
  latency_ms: number
  cost_usd: number | null
  model_provider: string
  model_name: string
  provider_version: string
  provider_error: ProviderErrorMetadata | null
  fallback_reason: string | null
  usage: TokenUsage
  evaluation_result: EvaluationResult
  batch_id: string | null
  input_source: InputSource
  baseline_score_delta: number | null
}

export interface AgentRun extends AgentRunSummary {
  final_answer: string
  retrieved_documents: RetrievedDocument[]
  tool_calls: ToolCall[]
}

export interface RunPage {
  items: AgentRunSummary[]
  total: number
  page: number
  page_size: number
  pages: number
  next_cursor?: string | null
}

export interface RunFilters {
  page?: number
  pageSize?: number
  cursor?: string
  status?: RunStatus | "all"
  severity?: Severity | "all"
  scenarioId?: string
  batchId?: string
  query?: string
}

export interface RunCreateRequest {
  mode: RunMode
  scenario_id: string | null
  input: string | null
  evaluation_spec_scenario_id: string | null
}

export interface BatchRun {
  id: string
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "degraded" | "failed"
  run_ids: string[]
  results: AgentRunSummary[]
  average_score: number | null
  pass_rate: number | null
  total_runs: number
  completed_runs: number
  failed_runs: number
  degraded_runs: number
  cancelled_runs: number
  queued_at: string | null
  last_heartbeat_at: string | null
  worker_id: string | null
  failure_reason: string | null
  retry_count: number
  repetitions: number
  aggregate_result: Record<string, unknown> | null
  configuration_snapshot: Record<string, unknown>
  selected_scenario_ids?: string[]
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface AgentConfig {
  id: number
  agent_name: string
  system_prompt: string
  model_mode: "mock" | "gemini"
  model_name: string | null
  temperature: number
  max_tool_calls: number
  request_timeout_seconds: number
  max_retries: number
  fallback_enabled: boolean
  version: number
  updated_at: string
}

export interface MetricsSummary {
  total_runs: number
  evaluated_runs?: number
  not_evaluated_runs?: number
  latest_pass_rate: number
  critical_failures: number
  average_latency_ms: number
  total_cost_usd?: number
  total_tokens?: number
  most_common_failure_reason: string | null
}

export interface Suite {
  id: string
  name: string
  description: string
  scenario_ids: string[]
  baseline_batch_id: string | null
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface SuiteWrite {
  name: string
  description: string
  scenario_ids: string[]
}

export type Severity = "low" | "medium" | "high" | "critical" | "ad_hoc"

export interface Scenario {
  id: string
  name: string
  input: string
  expected_tools: string[]
  must_not_include: string[]
  expected_behavior: string
  severity: Severity
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
  id: number
  tool_name: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  started_at: string
  finished_at: string
  latency_ms: number
  error: string | null
}

export interface EvaluationResult {
  passed: boolean
  score: number
  tool_call_correctness: number
  policy_compliance: number
  prompt_injection_resistance: number
  groundedness: number
  failure_reasons: string[]
  severity: Severity
}

export interface AgentRun {
  id: string
  scenario_id: string | null
  scenario_name: string | null
  input: string
  final_answer: string
  status: string
  started_at: string
  finished_at: string
  latency_ms: number
  estimated_cost_usd: number
  model_provider: string
  model_name: string
  retrieved_documents: RetrievedDocument[]
  evaluation_result: EvaluationResult
  tool_calls: ToolCall[]
}

export interface AgentConfig {
  id: number
  agent_name: string
  system_prompt: string
  model_mode: "mock" | "gemini"
  temperature: number
  max_tool_calls: number
  updated_at: string
}

export interface MetricsSummary {
  total_runs: number
  latest_pass_rate: number
  critical_failures: number
  average_latency_ms: number
  most_common_failure_reason: string | null
}

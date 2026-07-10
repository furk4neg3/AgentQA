"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import {
  AgentQAApiError,
  createBatchRun,
  createRun,
  getAgentConfig,
  getBatch,
  getMetricsSummary,
  getRun as fetchRun,
  listRuns,
  listScenarios,
  updateAgentConfig as saveAgentConfig,
  type AgentConfigPatch,
} from "./api"
import type {
  AgentConfig,
  AgentRun,
  AgentRunSummary,
  BatchRun,
  MetricsSummary,
  RunCreateRequest,
  RunFilters,
  RunPage,
  Scenario,
} from "./types"

interface StoreValue {
  scenarios: Scenario[]
  runs: AgentRunSummary[]
  runPage: Omit<RunPage, "items">
  runDetails: Record<string, AgentRun>
  detailLoading: Record<string, boolean>
  detailErrors: Record<string, AgentQAApiError | undefined>
  config: AgentConfig
  hydrated: boolean
  loading: boolean
  apiError: AgentQAApiError | null
  metrics: MetricsSummary
  refresh: (filters?: RunFilters) => Promise<void>
  refreshRuns: (filters?: RunFilters) => Promise<void>
  loadRunDetail: (id: string, options?: { signal?: AbortSignal; force?: boolean }) => Promise<AgentRun>
  runOnce: (payload: RunCreateRequest) => Promise<AgentRun>
  runBatch: (scenarioIds: string[], repetitions: number, baselineBatchId?: string | null) => Promise<BatchRun>
  getBatch: (batchId: string, options?: { signal?: AbortSignal }) => Promise<BatchRun>
  updateConfig: (patch: AgentConfigPatch) => Promise<AgentConfig>
  getRun: (id: string) => AgentRun | undefined
}

const EMPTY_METRICS: MetricsSummary = {
  total_runs: 0,
  latest_pass_rate: 0,
  critical_failures: 0,
  average_latency_ms: 0,
  most_common_failure_reason: null,
}

const EMPTY_CONFIG: AgentConfig = {
  id: 0,
  agent_name: "Loading…",
  system_prompt: "",
  model_mode: "mock",
  model_name: null,
  temperature: 0,
  max_tool_calls: 8,
  request_timeout_seconds: 30,
  max_retries: 2,
  fallback_enabled: false,
  version: 0,
  updated_at: new Date(0).toISOString(),
}

const EMPTY_PAGE: Omit<RunPage, "items"> = {
  total: 0,
  page: 1,
  page_size: 25,
  pages: 0,
  next_cursor: null,
}

const StoreContext = createContext<StoreValue | null>(null)

function toApiError(error: unknown): AgentQAApiError {
  if (error instanceof AgentQAApiError) return error
  return new AgentQAApiError("unknown", error instanceof Error ? error.message : "Unexpected AgentQA error")
}

function scenarioNames<T extends AgentRunSummary>(runs: T[], scenarios: Scenario[]): T[] {
  const names = new Map(scenarios.map((scenario) => [scenario.id, scenario.name]))
  return runs.map((run) => ({
    ...run,
    scenario_name: run.scenario_name ?? (run.scenario_id ? names.get(run.scenario_id) ?? null : null),
  })) as T[]
}

export function AgentQAProvider({ children }: { children: React.ReactNode }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [config, setConfig] = useState<AgentConfig>(EMPTY_CONFIG)
  const [runs, setRuns] = useState<AgentRunSummary[]>([])
  const [runPage, setRunPage] = useState<Omit<RunPage, "items">>(EMPTY_PAGE)
  const [runDetails, setRunDetails] = useState<Record<string, AgentRun>>({})
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({})
  const [detailErrors, setDetailErrors] = useState<Record<string, AgentQAApiError | undefined>>({})
  const [metrics, setMetrics] = useState<MetricsSummary>(EMPTY_METRICS)
  const [hydrated, setHydrated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState<AgentQAApiError | null>(null)
  const inFlightDetails = useRef(new Map<string, Promise<AgentRun>>())

  const refreshMetrics = useCallback(async () => {
    const nextMetrics = await getMetricsSummary()
    setMetrics(nextMetrics)
  }, [])

  const refresh = useCallback(async (filters: RunFilters = {}) => {
    setLoading(true)
    setApiError(null)
    try {
      const [nextScenarios, nextConfig, nextRunPage, nextMetrics] = await Promise.all([
        listScenarios(),
        getAgentConfig(),
        listRuns(filters),
        getMetricsSummary(),
      ])
      const { items, ...pagination } = nextRunPage
      setScenarios(nextScenarios)
      setConfig(nextConfig)
      setRuns(scenarioNames(items, nextScenarios))
      setRunPage(pagination)
      setMetrics(nextMetrics)
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setHydrated(true)
      setLoading(false)
    }
  }, [])

  const refreshRuns = useCallback(
    async (filters: RunFilters = {}) => {
      setLoading(true)
      setApiError(null)
      try {
        const nextRunPage = await listRuns(filters)
        const { items, ...pagination } = nextRunPage
        setRuns(scenarioNames(items, scenarios))
        setRunPage(pagination)
      } catch (error) {
        const apiError = toApiError(error)
        if (apiError.kind !== "cancelled") setApiError(apiError)
        throw apiError
      } finally {
        setLoading(false)
      }
    },
    [scenarios],
  )

  useEffect(() => {
    const timer = setTimeout(() => void refresh(), 0)
    return () => clearTimeout(timer)
  }, [refresh])

  const loadRunDetail = useCallback(
    async (id: string, options: { signal?: AbortSignal; force?: boolean } = {}) => {
      if (!options.force && runDetails[id]) return runDetails[id]
      const existing = inFlightDetails.current.get(id)
      if (!options.force && existing) return existing

      setDetailLoading((current) => ({ ...current, [id]: true }))
      setDetailErrors((current) => ({ ...current, [id]: undefined }))
      const pending = fetchRun(id, { signal: options.signal })
        .then((run) => {
          setRunDetails((current) => ({ ...current, [id]: run }))
          setRuns((current) => [run, ...current.filter((item) => item.id !== id)])
          return run
        })
        .catch((error) => {
          const apiError = toApiError(error)
          if (apiError.kind !== "cancelled") {
            setDetailErrors((current) => ({ ...current, [id]: apiError }))
          }
          throw apiError
        })
        .finally(() => {
          const nextInFlight = new Map(inFlightDetails.current)
          nextInFlight.delete(id)
          inFlightDetails.current = nextInFlight
          setDetailLoading((current) => ({ ...current, [id]: false }))
        })
      inFlightDetails.current = new Map(inFlightDetails.current).set(id, pending)
      return pending
    },
    [runDetails],
  )

  const runOnce = useCallback(
    async (payload: RunCreateRequest) => {
      setApiError(null)
      try {
        const run = await createRun(payload)
        const namedRun = scenarioNames([run], scenarios)[0]
        setRunDetails((current) => ({ ...current, [run.id]: namedRun }))
        setRuns((current) => [namedRun, ...current.filter((existing) => existing.id !== run.id)])
        await refreshMetrics()
        return namedRun
      } catch (error) {
        const apiError = toApiError(error)
        setApiError(apiError)
        throw apiError
      }
    },
    [refreshMetrics, scenarios],
  )

  const runBatch = useCallback(
    async (scenarioIds: string[], repetitions: number, baselineBatchId?: string | null) => {
      setApiError(null)
      try {
        const batch = await createBatchRun({
          scenario_ids: scenarioIds,
          repetitions,
          baseline_batch_id: baselineBatchId ?? null,
        })
        setRuns((current) => [
          ...scenarioNames(batch.results, scenarios),
          ...current.filter((existing) => !batch.run_ids.includes(existing.id)),
        ])
        await refreshMetrics()
        return batch
      } catch (error) {
        const apiError = toApiError(error)
        setApiError(apiError)
        throw apiError
      }
    },
    [refreshMetrics, scenarios],
  )

  const getBatchStatus = useCallback(
    (batchId: string, options: { signal?: AbortSignal } = {}) => getBatch(batchId, { signal: options.signal }),
    [],
  )

  const updateConfig = useCallback(async (patch: AgentConfigPatch) => {
    setApiError(null)
    try {
      const updated = await saveAgentConfig(patch)
      setConfig(updated)
      return updated
    } catch (error) {
      const apiError = toApiError(error)
      setApiError(apiError)
      throw apiError
    }
  }, [])

  const getRun = useCallback((id: string) => runDetails[id], [runDetails])

  const value = useMemo<StoreValue>(
    () => ({
      scenarios,
      runs,
      runPage,
      runDetails,
      detailLoading,
      detailErrors,
      config,
      hydrated,
      loading,
      apiError,
      metrics,
      refresh,
      refreshRuns,
      loadRunDetail,
      runOnce,
      runBatch,
      getBatch: getBatchStatus,
      updateConfig,
      getRun,
    }),
    [
      apiError,
      config,
      detailErrors,
      detailLoading,
      getBatchStatus,
      getRun,
      hydrated,
      loadRunDetail,
      loading,
      metrics,
      refresh,
      refreshRuns,
      runBatch,
      runDetails,
      runOnce,
      runPage,
      runs,
      scenarios,
      updateConfig,
    ],
  )

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useAgentQA(): StoreValue {
  const context = useContext(StoreContext)
  if (!context) throw new Error("useAgentQA must be used within AgentQAProvider")
  return context
}

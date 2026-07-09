"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import {
  createBatchRun,
  createRun,
  getAgentConfig,
  getMetricsSummary,
  getRun as fetchRun,
  listRuns,
  listScenarios,
  updateAgentConfig as saveAgentConfig,
  type AgentConfigPatch,
} from "./api"
import { DEFAULT_AGENT_CONFIG, SCENARIOS } from "./seed"
import type { AgentConfig, AgentRun, MetricsSummary, Scenario } from "./types"

interface BatchResult {
  run_ids: string[]
  results: AgentRun[]
  average_score: number
  pass_rate: number
}

interface StoreValue {
  scenarios: Scenario[]
  runs: AgentRun[]
  config: AgentConfig
  hydrated: boolean
  loading: boolean
  apiError: string | null
  metrics: MetricsSummary
  refresh: () => Promise<void>
  runOnce: (scenarioId: string | null, input: string) => Promise<AgentRun>
  runBatch: () => Promise<BatchResult>
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

const StoreContext = createContext<StoreValue | null>(null)

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Unexpected backend error"
}

function addScenarioName(run: AgentRun, scenarios: Scenario[]): AgentRun {
  const scenarioName = scenarios.find((scenario) => scenario.id === run.scenario_id)?.name ?? null
  return { ...run, scenario_name: scenarioName }
}

async function loadRunDetails(runIds: string[], scenarios: Scenario[]): Promise<AgentRun[]> {
  const details = await Promise.all(
    runIds.map(async (runId) => {
      try {
        return addScenarioName(await fetchRun(runId), scenarios)
      } catch {
        return null
      }
    }),
  )
  return details.filter((run): run is AgentRun => run !== null)
}

export function AgentQAProvider({ children }: { children: React.ReactNode }) {
  const [scenarios, setScenarios] = useState<Scenario[]>(SCENARIOS)
  const [config, setConfig] = useState<AgentConfig>(DEFAULT_AGENT_CONFIG)
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [metrics, setMetrics] = useState<MetricsSummary>(EMPTY_METRICS)
  const [hydrated, setHydrated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const refreshMetrics = useCallback(async () => {
    setMetrics(await getMetricsSummary())
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setApiError(null)
    try {
      const [nextScenarios, nextConfig, runSummaries, nextMetrics] = await Promise.all([
        listScenarios(),
        getAgentConfig(),
        listRuns(),
        getMetricsSummary(),
      ])
      const nextRuns = await loadRunDetails(
        runSummaries.map((run) => run.id),
        nextScenarios,
      )

      setScenarios(nextScenarios)
      setConfig(nextConfig)
      setRuns(nextRuns)
      setMetrics(nextMetrics)
    } catch (error) {
      setApiError(toErrorMessage(error))
    } finally {
      setHydrated(true)
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const runOnce = useCallback(
    async (scenarioId: string | null, input: string) => {
      setApiError(null)
      try {
        const run = addScenarioName(await createRun({ scenario_id: scenarioId, input }), scenarios)
        setRuns((prev) => [run, ...prev.filter((existing) => existing.id !== run.id)])
        await refreshMetrics()
        return run
      } catch (error) {
        const message = toErrorMessage(error)
        setApiError(message)
        throw new Error(message)
      }
    },
    [refreshMetrics, scenarios],
  )

  const runBatch = useCallback(async (): Promise<BatchResult> => {
    setApiError(null)
    try {
      const result = await createBatchRun(scenarios.map((scenario) => scenario.id))
      const detailedRuns = await loadRunDetails(result.run_ids, scenarios)
      setRuns((prev) => [
        ...detailedRuns,
        ...prev.filter((existing) => !result.run_ids.includes(existing.id)),
      ])
      await refreshMetrics()
      return {
        run_ids: result.run_ids,
        results: detailedRuns,
        average_score: result.average_score,
        pass_rate: result.pass_rate,
      }
    } catch (error) {
      const message = toErrorMessage(error)
      setApiError(message)
      throw new Error(message)
    }
  }, [refreshMetrics, scenarios])

  const updateConfig = useCallback(async (patch: AgentConfigPatch) => {
    setApiError(null)
    try {
      const updated = await saveAgentConfig(patch)
      setConfig(updated)
      return updated
    } catch (error) {
      const message = toErrorMessage(error)
      setApiError(message)
      throw new Error(message)
    }
  }, [])

  const getRun = useCallback((id: string) => runs.find((run) => run.id === id), [runs])

  const value = useMemo<StoreValue>(
    () => ({
      scenarios,
      runs,
      config,
      hydrated,
      loading,
      apiError,
      metrics,
      refresh,
      runOnce,
      runBatch,
      updateConfig,
      getRun,
    }),
    [apiError, config, getRun, hydrated, loading, metrics, refresh, runBatch, runOnce, runs, scenarios, updateConfig],
  )

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useAgentQA(): StoreValue {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error("useAgentQA must be used within AgentQAProvider")
  return ctx
}

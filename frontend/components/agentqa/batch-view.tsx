"use client"

import { useEffect, useRef, useState } from "react"
import { Layers, Loader, Play } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { listBatches } from "@/lib/agentqa/api"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRunSummary, BatchRun } from "@/lib/agentqa/types"
import { formatScore, scoreColor, SeverityBadge, StatusPill } from "./shared"

const TERMINAL_BATCH_STATUSES = new Set(["completed", "degraded", "failed", "cancelled"])

export function BatchView({ onOpenTrace }: { onOpenTrace: (id: string) => void }) {
  const { scenarios, hydrated, getBatch, runBatch } = useAgentQA()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [repetitions, setRepetitions] = useState(1)
  const [baselineBatchId, setBaselineBatchId] = useState("")
  const [baselineOptions, setBaselineOptions] = useState<BatchRun[]>([])
  const [running, setRunning] = useState(false)
  const [batch, setBatch] = useState<BatchRun | null>(null)
  const selectionInitialized = useRef(false)
  const pollController = useRef<AbortController | null>(null)

  useEffect(() => {
    if (selectionInitialized.current || !scenarios.length) return
    selectionInitialized.current = true
    setSelectedIds(scenarios.map((scenario) => scenario.id))
  }, [scenarios])

  useEffect(() => () => pollController.current?.abort(), [])

  useEffect(() => {
    const controller = new AbortController()
    void listBatches(1, 25, { signal: controller.signal })
      .then((items) =>
        setBaselineOptions(items.filter((item) => TERMINAL_BATCH_STATUSES.has(item.status))),
      )
      .catch((error) => {
        if (!controller.signal.aborted) {
          toast.error("Could not load baseline batches", {
            description: error instanceof Error ? error.message : "Unknown baseline request error",
          })
        }
      })
    return () => controller.abort()
  }, [])

  const pollBatch = async (initial: BatchRun, signal: AbortSignal) => {
    let current = initial
    while (!TERMINAL_BATCH_STATUSES.has(current.status) && !signal.aborted) {
      await new Promise<void>((resolve) => setTimeout(resolve, 750))
      current = await getBatch(current.id, { signal })
      setBatch(current)
    }
    return current
  }

  const handleRun = async () => {
    if (!selectedIds.length) return
    pollController.current?.abort()
    const controller = new AbortController()
    pollController.current = controller
    setRunning(true)
    try {
      const started = await runBatch(selectedIds, repetitions, baselineBatchId || null)
      setBatch(started)
      const result = await pollBatch(started, controller.signal)
      if (result.status === "failed") {
        toast.error("Batch evaluation failed", {
          description: `${result.failed_runs} of ${result.total_runs} runs failed to execute.`,
        })
      } else {
        toast.success(result.status === "degraded" ? "Batch completed with partial failures" : "Batch evaluation complete", {
          description: `${formatPercent(result.pass_rate)} pass rate across ${result.completed_runs} completed runs`,
        })
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        toast.error("Batch evaluation failed", {
          description: error instanceof Error ? error.message : "Could not run suite",
        })
      }
    } finally {
      if (pollController.current === controller) setRunning(false)
    }
  }

  const toggleScenario = (id: string) => {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((scenarioId) => scenarioId !== id) : [...current, id],
    )
  }

  const passed = batch?.results.filter((run) => run.evaluation_result.passed === true).length ?? 0
  const evaluatedFailed = batch?.results.filter((run) => run.evaluation_result.passed === false).length ?? 0
  const processedRuns = batch
    ? batch.completed_runs + batch.degraded_runs + batch.failed_runs + batch.cancelled_runs
    : 0
  const progress = batch?.total_runs
    ? Math.min(100, Math.round((processedRuns / batch.total_runs) * 100))
    : 0

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Regression</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Batch Evaluation</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Select scenarios and repetitions, then monitor every success, degradation, and provider failure.
          </p>
        </div>
        <Button onClick={handleRun} disabled={running || !hydrated || !selectedIds.length} className="gap-2 self-start sm:self-auto">
          {running ? <Loader className="size-4 animate-spin" /> : <Play className="size-4" />}
          {running ? "Evaluating suite..." : `Run ${selectedIds.length} Scenario${selectedIds.length === 1 ? "" : "s"}`}
        </Button>
      </header>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <CardTitle className="text-base">Batch configuration</CardTitle>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSelectedIds(selectedIds.length === scenarios.length ? [] : scenarios.map((scenario) => scenario.id))}
          >
            {selectedIds.length === scenarios.length ? "Clear all" : "Select all"}
          </Button>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-[1fr_10rem_18rem]">
          <fieldset>
            <legend className="sr-only">Scenarios included in this batch</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {scenarios.map((scenario) => (
                <label key={scenario.id} className="flex cursor-pointer items-start gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2.5 hover:bg-muted/40">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(scenario.id)}
                    onChange={() => toggleScenario(scenario.id)}
                    className="mt-0.5 size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{scenario.name}</span>
                    <span className="mt-1 block"><SeverityBadge severity={scenario.severity} /></span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-col gap-2">
            <Label htmlFor="repetitions">Repetitions</Label>
            <Input
              id="repetitions"
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={repetitions}
              onChange={(event) => setRepetitions(Math.min(20, Math.max(1, Number(event.target.value) || 1)))}
            />
            <p className="text-xs text-muted-foreground">Repeat each selected scenario for nondeterministic models.</p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="baseline-batch">Regression baseline</Label>
            <select
              id="baseline-batch"
              value={baselineBatchId}
              onChange={(event) => setBaselineBatchId(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">No baseline</option>
              {baselineOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {formatBatchOption(option)}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Compare each scenario score and aggregate pass rate with a completed batch.
            </p>
          </div>
        </CardContent>
      </Card>

      {!batch ? (
        <Card className="flex items-center justify-center border-dashed">
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted"><Layers className="size-5 text-muted-foreground" /></div>
            <p className="max-w-sm text-sm text-muted-foreground">Launch a batch to see persistent progress and per-run results.</p>
          </div>
        </Card>
      ) : (
        <>
          <Card aria-live="polite">
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">Batch {batch.id}</span>
                <span className="font-mono text-muted-foreground">{processedRuns} / {batch.total_runs} processed</span>
              </div>
              <div
                role="progressbar"
                aria-label="Batch completion"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
                className="h-2 overflow-hidden rounded-full bg-muted"
              >
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">Status: {batch.status}</p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-8">
            <SummaryCard label="Pass Rate" value={formatPercent(batch.pass_rate)} accent />
            <SummaryCard label="Avg Score" value={formatScore(batch.average_score)} />
            <SummaryCard label="Score Δ" value={formatDelta(recordNumber(batch.aggregate_result, "score_delta"))} />
            <SummaryCard label="Pass Rate Δ" value={formatPercentDelta(recordNumber(batch.aggregate_result, "pass_rate_delta"))} />
            <SummaryCard label="Passed" value={passed.toString()} tone="success" />
            <SummaryCard label="Eval Failed" value={evaluatedFailed.toString()} tone={evaluatedFailed ? "danger" : undefined} />
            <SummaryCard label="Provider Failed" value={batch.failed_runs.toString()} tone={batch.failed_runs ? "danger" : undefined} />
            <SummaryCard label="Degraded" value={batch.degraded_runs.toString()} tone={batch.degraded_runs ? "warning" : undefined} />
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">Scenario Results</CardTitle></CardHeader>
            <CardContent className="px-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-6">Status</TableHead>
                      <TableHead>Scenario</TableHead>
                      <TableHead className="text-right">Score</TableHead>
                      <TableHead className="text-right">Latency</TableHead>
                      <TableHead>Severity</TableHead>
                      <TableHead>Baseline Δ</TableHead>
                      <TableHead className="pr-6">Evidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {batch.results.map((run) => (
                      <ResultRow key={run.id} run={run} onOpenTrace={onOpenTrace} />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function ResultRow({ run, onOpenTrace }: { run: AgentRunSummary; onOpenTrace: (id: string) => void }) {
  const evaluation = run.evaluation_result
  const open = () => onOpenTrace(run.id)
  return (
    <TableRow
      tabIndex={0}
      role="button"
      aria-label={`Open trace for ${run.scenario_name ?? "ad-hoc run"}`}
      className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          open()
        }
      }}
    >
      <TableCell className="pl-6"><StatusPill passed={evaluation.passed} outcome={evaluation.outcome} status={run.status} /></TableCell>
      <TableCell className="max-w-56">
        <p className="truncate text-sm font-medium">{run.scenario_name ?? "Ad-hoc run"}</p>
        <p className="truncate font-mono text-xs text-muted-foreground">{run.input}</p>
      </TableCell>
      <TableCell className={`text-right font-mono ${scoreColor(evaluation.score)}`}>{formatScore(evaluation.score)}</TableCell>
      <TableCell className="text-right font-mono text-sm text-muted-foreground">{run.latency_ms}ms</TableCell>
      <TableCell><SeverityBadge severity={evaluation.severity} /></TableCell>
      <TableCell className="font-mono text-xs">{formatDelta(run.baseline_score_delta)}</TableCell>
      <TableCell className="max-w-64 pr-6">
        {run.provider_error ? (
          <span className="line-clamp-2 text-xs text-destructive">Provider: {run.provider_error.message}</span>
        ) : evaluation.failure_reasons.length ? (
          <span className="line-clamp-2 text-xs text-destructive">{evaluation.failure_reasons.join("; ")}</span>
        ) : (
          <span className="font-mono text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  )
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`
}

function formatDelta(value: number | null): string {
  if (value === null) return "—"
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`
}

function recordNumber(record: Record<string, unknown> | null, key: string): number | null {
  const value = record?.[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function formatPercentDelta(value: number | null): string {
  if (value === null) return "—"
  const percentage = Math.round(value * 100)
  return `${percentage > 0 ? "+" : ""}${percentage}%`
}

function formatBatchOption(batch: BatchRun): string {
  const date = batch.created_at ?? batch.started_at
  const dateLabel = date ? new Date(date).toLocaleString() : "Unknown date"
  return `${dateLabel} · ${formatPercent(batch.pass_rate)} · ${batch.status}`
}

function SummaryCard({ label, value, accent, tone }: { label: string; value: string; accent?: boolean; tone?: "success" | "danger" | "warning" }) {
  const valueClass = tone === "danger" ? "text-destructive" : tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : accent ? "text-primary" : "text-foreground"
  return (
    <Card>
      <CardContent className="p-4">
        <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-2 text-3xl font-semibold tracking-tight ${valueClass}`}>{value}</p>
      </CardContent>
    </Card>
  )
}

"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import {
  Activity,
  Check,
  Clock,
  Coins,
  Cpu,
  Database,
  Filter,
  Gauge,
  MessageSquare,
  Route,
  Search,
  ShieldAlert,
  Wrench,
  X,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { TOOL_LABELS } from "@/lib/agentqa/tool-labels"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun, RunStatus, Severity, ToolCall } from "@/lib/agentqa/types"
import {
  formatCost,
  formatRelativeTime,
  formatScore,
  formatTokens,
  formatTime,
  scoreColor,
  SeverityBadge,
  StatusPill,
} from "./shared"
import { EvaluationChecks, FailureReasons, MetricBars, RetrievedDocs, ToolTrace } from "./evaluation-panels"

type StatusFilter = "all" | RunStatus
type SeverityFilter = "all" | Severity

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "degraded", label: "Degraded" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
]

const SEVERITY_OPTIONS: { value: SeverityFilter; label: string }[] = [
  { value: "all", label: "All severities" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "ad_hoc", label: "Ad hoc" },
]

export function TracesView({ focusRunId }: { focusRunId: string | null }) {
  const {
    detailErrors,
    detailLoading,
    getRun,
    hydrated,
    loadRunDetail,
    refreshRuns,
    runPage,
    runs,
  } = useAgentQA()
  const [chosenId, setChosenId] = useState<string | null>(focusRunId)
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all")
  const [page, setPage] = useState(1)
  const filtersReady = useRef(false)

  const selectedId = chosenId ?? focusRunId ?? runs[0]?.id ?? null

  useEffect(() => {
    if (!selectedId) return

    void loadRunDetail(selectedId).catch(() => undefined)
  }, [loadRunDetail, selectedId])

  useEffect(() => {
    if (!hydrated) return
    if (!filtersReady.current) {
      filtersReady.current = true
      return
    }
    const timer = setTimeout(() => {
      void refreshRuns({
        page,
        pageSize: runPage.page_size,
        query,
        status: statusFilter,
        severity: severityFilter,
      }).catch(() => undefined)
    }, 250)
    return () => clearTimeout(timer)
  }, [hydrated, page, query, refreshRuns, runPage.page_size, severityFilter, statusFilter])

  const selected = selectedId ? getRun(selectedId) ?? null : null
  const selectedSummary = runs.find((run) => run.id === selectedId) ?? null
  const selectedError = selectedId ? detailErrors[selectedId] : undefined
  const selectedLoading = selectedId ? detailLoading[selectedId] === true : false
  const traceSummary = useMemo(() => summarizeTrace(selected), [selected])
  const timeline = useMemo(() => buildTimeline(selected), [selected])

  const updateStatus = (value: string | null) => {
    if (!value) return
    setStatusFilter(value as StatusFilter)
    setPage(1)
  }
  const updateSeverity = (value: string | null) => {
    if (!value) return
    setSeverityFilter(value as SeverityFilter)
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Introspection</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Trace Viewer</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Browse paginated run summaries, then load a full trace only when you select it.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader className="gap-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base">Runs ({runs.length})</CardTitle>
              <span className="font-mono text-[11px] text-muted-foreground">{runPage.total} total</span>
            </div>
            <div className="flex flex-col gap-2">
              <div className="relative">
                <Label htmlFor="trace-search" className="sr-only">Search runs</Label>
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  id="trace-search"
                  value={query}
                  onChange={(event) => { setQuery(event.target.value); setPage(1) }}
                  placeholder="Search run or prompt..."
                  className="h-8 pl-8 font-mono text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="trace-status" className="sr-only">Filter by status</Label>
                  <Select value={statusFilter} onValueChange={updateStatus}>
                    <SelectTrigger id="trace-status" className="w-full" size="sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {STATUS_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="trace-severity" className="sr-only">Filter by severity</Label>
                  <Select value={severityFilter} onValueChange={updateSeverity}>
                    <SelectTrigger id="trace-severity" className="w-full" size="sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SEVERITY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <ScrollArea className="h-[560px]">
              <div className="flex flex-col gap-1 px-3 pb-3">
                {runs.map((run) => (
                  <button
                    type="button"
                    key={run.id}
                    onClick={() => setChosenId(run.id)}
                    aria-current={selectedId === run.id ? "true" : undefined}
                    className={cn(
                      "flex flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selectedId === run.id ? "border-primary/40 bg-accent/50" : "border-transparent hover:bg-accent/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <StatusPill passed={run.evaluation_result.passed} outcome={run.evaluation_result.outcome} status={run.status} />
                      <span className="font-mono text-[10px] text-muted-foreground">{formatRelativeTime(run.started_at)}</span>
                    </div>
                    <p className="truncate text-sm font-medium">{run.scenario_name ?? "Ad-hoc run"}</p>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                      <span className={scoreColor(run.evaluation_result.score)}>{formatScore(run.evaluation_result.score)}</span>
                      <span>·</span><span>{run.latency_ms}ms</span><span>·</span><span className="truncate">{run.id}</span>
                    </div>
                  </button>
                ))}
                {!runs.length && (
                  <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center">
                    <Filter className="mx-auto mb-2 size-4 text-muted-foreground" aria-hidden="true" />
                    <p className="text-sm text-muted-foreground">No runs match these filters.</p>
                  </div>
                )}
              </div>
            </ScrollArea>
            <div className="flex items-center justify-between border-t border-border px-3 py-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</Button>
              <span className="font-mono text-[11px] text-muted-foreground">Page {runPage.pages ? page : 0} of {runPage.pages}</span>
              <Button variant="outline" size="sm" disabled={page >= runPage.pages} onClick={() => setPage((current) => current + 1)}>Next</Button>
            </div>
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
          {!selectedId ? (
            <EmptyDetail message="No runs available yet." />
          ) : selectedError ? (
            <Card role="alert" className="border-destructive/30">
              <CardContent className="flex flex-col items-start gap-3 p-6">
                <p className="font-medium text-destructive">Could not load this run trace</p>
                <p className="text-sm text-muted-foreground">{errorLabel(selectedError.kind)}: {selectedError.message}</p>
                <Button variant="outline" size="sm" onClick={() => void loadRunDetail(selectedId, { force: true }).catch(() => undefined)}>Retry detail</Button>
              </CardContent>
            </Card>
          ) : selectedLoading || !selected ? (
            <Card aria-busy="true">
              <CardContent className="flex items-center gap-3 p-6 text-sm text-muted-foreground">
                <LoaderIndicator /> Loading full trace for {selectedSummary?.scenario_name ?? selectedId}…
              </CardContent>
            </Card>
          ) : (
            <TraceDetail selected={selected} traceSummary={traceSummary} timeline={timeline} />
          )}
        </div>
      </div>
    </div>
  )
}

function LoaderIndicator() {
  return <span className="size-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" aria-hidden="true" />
}

function EmptyDetail({ message }: { message: string }) {
  return <Card className="flex h-full items-center justify-center border-dashed"><p className="py-16 text-sm text-muted-foreground">{message}</p></Card>
}

function TraceDetail({ selected, traceSummary, timeline }: { selected: AgentRun; traceSummary: ReturnType<typeof summarizeTrace>; timeline: ReturnType<typeof buildTimeline> }) {
  const evaluation = selected.evaluation_result
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <StatusPill passed={evaluation.passed} outcome={evaluation.outcome} status={selected.status} />
                <SeverityBadge severity={evaluation.severity} />
              </div>
              <p className="truncate text-base font-medium">{selected.scenario_name ?? "Ad-hoc run"}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{selected.id}</p>
            </div>
            <span className="rounded-full border border-border bg-muted px-2 py-1 font-mono text-[11px] uppercase text-muted-foreground">{selected.input_source}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <TraceStat icon={MessageSquare} label="Score" value={formatScore(evaluation.score)} />
            <TraceStat icon={Clock} label="Latency" value={`${selected.latency_ms}ms`} />
            <TraceStat icon={Coins} label="Cost" value={formatCost(selected.cost_usd)} />
            <TraceStat icon={Gauge} label="Tokens" value={formatTokens(selected.usage.total_tokens)} />
          </div>
          {(selected.provider_error || selected.fallback_reason) && (
            <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm text-warning">
              {selected.provider_error && <p>Provider error ({selected.provider_error.category}): {selected.provider_error.message}</p>}
              {selected.fallback_reason && <p>Fallback reason: {selected.fallback_reason}</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <TraceStat icon={Wrench} label="Tool calls" value={String(traceSummary.toolCalls)} />
        <TraceStat icon={Database} label="Policy docs" value={String(traceSummary.docs)} />
        <TraceStat icon={ShieldAlert} label="Failed checks" value={String(traceSummary.failures)} />
        <TraceStat icon={Cpu} label="Model" value={selected.model_name} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Conversation</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="rounded-lg border border-border bg-muted/40 p-3">
            <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">User input</p>
            <p className="text-sm leading-relaxed">{selected.input}</p>
          </div>
          <div className="rounded-lg border border-primary/25 bg-primary/5 p-3">
            <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-primary">Agent answer</p>
            <p className="text-sm leading-relaxed text-pretty">{selected.final_answer || "No final answer was produced."}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base">Run Timeline</CardTitle><Route className="size-4 text-muted-foreground" /></CardHeader>
        <CardContent>
          <ol className="relative flex flex-col gap-3 before:absolute before:left-3 before:top-3 before:h-[calc(100%-1.5rem)] before:w-px before:bg-border">
            {timeline.map((event) => (
              <li key={event.id} className="relative flex gap-3">
                <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border bg-card", event.tone === "success" && "border-success/40 text-success", event.tone === "danger" && "border-destructive/40 text-destructive", event.tone === "primary" && "border-primary/40 text-primary", event.tone === "muted" && "border-border text-muted-foreground")}>
                  <event.icon className="size-3.5" />
                </span>
                <div className="min-w-0 flex-1 rounded-lg border border-border bg-muted/30 px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">{event.label}</p><span className="font-mono text-[11px] text-muted-foreground">{event.meta}</span></div>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{event.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card><CardHeader><CardTitle className="text-base">Tool Trace</CardTitle></CardHeader><CardContent><ToolTrace toolCalls={selected.tool_calls} /></CardContent></Card>

      <div className="grid grid-cols-1 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Evaluation</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-5">
            {evaluation.outcome === "not_evaluated" ? (
              <p className="rounded-lg border border-border bg-muted/40 px-3 py-3 text-sm text-muted-foreground">Not evaluated — no evaluation specification was selected for this run.</p>
            ) : (
              <><MetricBars evaluation={evaluation} /><EvaluationChecks checks={evaluation.checks} /><FailureReasons reasons={evaluation.failure_reasons} /></>
            )}
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-base">Retrieved Policy</CardTitle></CardHeader><CardContent><RetrievedDocs docs={selected.retrieved_documents} /></CardContent></Card>
      </div>
    </div>
  )
}

function errorLabel(kind: string): string {
  if (kind === "connection") return "Connection error"
  if (kind === "validation") return "Validation error"
  if (kind === "provider") return "Provider error"
  if (kind === "timeout") return "Request timeout"
  return "Request error"
}

function summarizeTrace(run: AgentRun | null) {
  if (!run) return { toolCalls: 0, docs: 0, failures: 0 }
  return {
    toolCalls: run.tool_calls.length,
    docs: run.retrieved_documents.length,
    failures: run.evaluation_result.checks.filter((check) => !check.passed).length || run.evaluation_result.failure_reasons.length,
  }
}

function buildTimeline(run: AgentRun | null) {
  if (!run) return []
  const evaluation = run.evaluation_result
  const evaluationPassed = evaluation.passed === true
  return [
    { id: `${run.id}-input`, icon: MessageSquare, tone: "muted" as const, label: "User message received", meta: formatTime(run.started_at), detail: run.input },
    ...run.tool_calls.map((call) => toolEvent(run.id, call)),
    { id: `${run.id}-answer`, icon: Activity, tone: run.status === "failed" ? ("danger" as const) : ("primary" as const), label: run.status === "failed" ? "Agent execution failed" : "Agent answer completed", meta: `${run.latency_ms}ms total`, detail: run.provider_error?.message ?? run.final_answer },
    {
      id: `${run.id}-evaluation`,
      icon: evaluation.outcome === "not_evaluated" ? ShieldAlert : evaluationPassed ? Check : X,
      tone: evaluation.outcome === "not_evaluated" ? ("muted" as const) : evaluationPassed ? ("success" as const) : ("danger" as const),
      label: evaluation.outcome === "not_evaluated" ? "Run not evaluated" : evaluationPassed ? "Evaluation passed" : "Evaluation failed",
      meta: evaluation.score === null ? "no score" : `score ${formatScore(evaluation.score)}`,
      detail: evaluation.failure_reasons.length ? evaluation.failure_reasons.join("; ") : evaluation.outcome === "not_evaluated" ? "No evaluation specification was selected." : "All configured checks passed for this run.",
    },
  ]
}

function toolEvent(runId: string, call: ToolCall) {
  return { id: `${runId}-tool-${call.id ?? call.started_at}`, icon: Wrench, tone: call.error ? ("danger" as const) : ("primary" as const), label: TOOL_LABELS[call.tool_name] ?? call.tool_name, meta: `${call.latency_ms}ms`, detail: call.error ?? `Input ${JSON.stringify(call.input)} -> Output ${JSON.stringify(call.output)}` }
}

function TraceStat({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-muted-foreground"><Icon className="size-3.5" /><span className="font-mono text-[11px] uppercase tracking-wide">{label}</span></div>
      <p className="truncate font-mono text-sm">{value}</p>
    </div>
  )
}

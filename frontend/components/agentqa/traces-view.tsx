"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  Check,
  Clock,
  Copy,
  Cpu,
  Database,
  DollarSign,
  Filter,
  MessageSquare,
  Route,
  Search,
  ShieldAlert,
  Timer,
  Wrench,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { TOOL_LABELS } from "@/lib/agentqa/seed"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun, Severity, ToolCall } from "@/lib/agentqa/types"
import {
  formatCost,
  formatRelativeTime,
  formatTime,
  scoreColor,
  SeverityBadge,
  StatusPill,
} from "./shared"
import { FailureReasons, MetricBars, RetrievedDocs, ToolTrace } from "./evaluation-panels"

type StatusFilter = "all" | "passed" | "failed"
type SeverityFilter = "all" | Severity

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "passed", label: "Passed only" },
  { value: "failed", label: "Failed only" },
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
  const { runs } = useAgentQA()
  const [selectedId, setSelectedId] = useState<string | null>(focusRunId ?? runs[0]?.id ?? null)
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all")

  useEffect(() => {
    if (focusRunId) setSelectedId(focusRunId)
  }, [focusRunId])

  const selected = useMemo(
    () => runs.find((r) => r.id === selectedId) ?? runs[0] ?? null,
    [runs, selectedId],
  )

  const filteredRuns = useMemo(
    () => filterRuns(runs, query, statusFilter, severityFilter),
    [runs, query, statusFilter, severityFilter],
  )

  const traceSummary = useMemo(() => summarizeTrace(selected), [selected])
  const timeline = useMemo(() => buildTimeline(selected), [selected])

  const copyRunJson = async () => {
    if (!selected) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(selected, null, 2))
      toast.success("Run JSON copied")
    } catch {
      toast.error("Could not copy run JSON")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Introspection</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Trace Viewer</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Step through any run&apos;s tool trace, retrieved policy, and evaluation detail.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Run list */}
        <Card className="lg:col-span-1">
          <CardHeader className="gap-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base">Runs ({filteredRuns.length})</CardTitle>
              <span className="font-mono text-[11px] text-muted-foreground">{runs.length} total</span>
            </div>
            <div className="flex flex-col gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search run, prompt, tool..."
                  className="h-8 pl-8 font-mono text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
                  <SelectTrigger className="w-full" size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={severityFilter} onValueChange={(value) => setSeverityFilter(value as SeverityFilter)}>
                  <SelectTrigger className="w-full" size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <ScrollArea className="h-[560px]">
              <div className="flex flex-col gap-1 px-3 pb-3">
                {filteredRuns.map((run) => (
                  <button
                    key={run.id}
                    onClick={() => setSelectedId(run.id)}
                    className={cn(
                      "flex flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors",
                      selected?.id === run.id
                        ? "border-primary/40 bg-accent/50"
                        : "border-transparent hover:bg-accent/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <StatusPill passed={run.evaluation_result.passed} />
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {formatRelativeTime(run.started_at)}
                      </span>
                    </div>
                    <p className="truncate text-sm font-medium">{run.scenario_name ?? "Ad-hoc run"}</p>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                      <span className={scoreColor(run.evaluation_result.score)}>
                        {run.evaluation_result.score.toFixed(2)}
                      </span>
                      <span>·</span>
                      <span>{run.latency_ms}ms</span>
                      <span>·</span>
                      <span className="truncate">{run.id}</span>
                    </div>
                  </button>
                ))}
                {!filteredRuns.length && (
                  <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center">
                    <Filter className="mx-auto mb-2 size-4 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">No runs match these filters.</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Detail */}
        <div className="lg:col-span-2">
          {!selected ? (
            <Card className="flex h-full items-center justify-center border-dashed">
              <p className="py-16 text-sm text-muted-foreground">No runs available yet.</p>
            </Card>
          ) : (
            <div className="flex flex-col gap-4">
              <Card>
                <CardContent className="flex flex-col gap-4 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <StatusPill passed={selected.evaluation_result.passed} />
                        <SeverityBadge severity={selected.evaluation_result.severity} />
                      </div>
                      <p className="truncate text-base font-medium">{selected.scenario_name ?? "Ad-hoc run"}</p>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">{selected.id}</p>
                    </div>
                    <Button variant="outline" size="sm" className="gap-2" onClick={copyRunJson}>
                      <Copy className="size-3.5" />
                      Copy JSON
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <TraceStat icon={MessageSquare} label="Score" value={selected.evaluation_result.score.toFixed(2)} />
                    <TraceStat icon={Clock} label="Latency" value={`${selected.latency_ms}ms`} />
                    <TraceStat icon={DollarSign} label="Cost" value={formatCost(selected.estimated_cost_usd)} />
                    <TraceStat icon={Cpu} label="Model" value={selected.model_name} />
                  </div>
                </CardContent>
              </Card>

              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <TraceStat icon={Wrench} label="Tool calls" value={String(traceSummary.toolCalls)} />
                <TraceStat icon={Database} label="Policy docs" value={String(traceSummary.docs)} />
                <TraceStat icon={ShieldAlert} label="Failures" value={String(traceSummary.failures)} />
                <TraceStat icon={Timer} label="Started" value={formatTime(selected.started_at)} />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Conversation</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="rounded-lg border border-border bg-muted/40 p-3">
                    <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                      User input
                    </p>
                    <p className="text-sm leading-relaxed">{selected.input}</p>
                  </div>
                  <div className="rounded-lg border border-primary/25 bg-primary/5 p-3">
                    <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-primary">Agent answer</p>
                    <p className="text-sm leading-relaxed text-pretty">{selected.final_answer}</p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-base">Run Timeline</CardTitle>
                  <Route className="size-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <ol className="relative flex flex-col gap-3 before:absolute before:left-3 before:top-3 before:h-[calc(100%-1.5rem)] before:w-px before:bg-border">
                    {timeline.map((event) => (
                      <li key={event.id} className="relative flex gap-3">
                        <span
                          className={cn(
                            "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border bg-card",
                            event.tone === "success" && "border-success/40 text-success",
                            event.tone === "danger" && "border-destructive/40 text-destructive",
                            event.tone === "primary" && "border-primary/40 text-primary",
                            event.tone === "muted" && "border-border text-muted-foreground",
                          )}
                        >
                          <event.icon className="size-3.5" />
                        </span>
                        <div className="min-w-0 flex-1 rounded-lg border border-border bg-muted/30 px-3 py-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-medium">{event.label}</p>
                            <span className="font-mono text-[11px] text-muted-foreground">{event.meta}</span>
                          </div>
                          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                            {event.detail}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Tool Trace</CardTitle>
                </CardHeader>
                <CardContent>
                  <ToolTrace toolCalls={selected.tool_calls} />
                </CardContent>
              </Card>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Evaluation</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-5">
                    <MetricBars evaluation={selected.evaluation_result} />
                    <FailureReasons reasons={selected.evaluation_result.failure_reasons} />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Retrieved Policy</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <RetrievedDocs docs={selected.retrieved_documents} />
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function filterRuns(
  runs: AgentRun[],
  query: string,
  statusFilter: StatusFilter,
  severityFilter: SeverityFilter,
): AgentRun[] {
  const q = query.trim().toLowerCase()
  return runs.filter((run) => {
    if (statusFilter === "passed" && !run.evaluation_result.passed) return false
    if (statusFilter === "failed" && run.evaluation_result.passed) return false
    if (severityFilter !== "all" && run.evaluation_result.severity !== severityFilter) return false
    if (!q) return true
    const haystack = [
      run.id,
      run.scenario_name,
      run.input,
      run.final_answer,
      run.model_name,
      run.model_provider,
      run.evaluation_result.failure_reasons.join(" "),
      run.tool_calls.map((call) => `${call.tool_name} ${JSON.stringify(call.input)} ${JSON.stringify(call.output)}`).join(" "),
      run.retrieved_documents.map((doc) => `${doc.title} ${doc.snippet}`).join(" "),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
    return haystack.includes(q)
  })
}

function summarizeTrace(run: AgentRun | null) {
  if (!run) return { toolCalls: 0, docs: 0, failures: 0 }
  return {
    toolCalls: run.tool_calls.length,
    docs: run.retrieved_documents.length,
    failures: run.evaluation_result.failure_reasons.length,
  }
}

function buildTimeline(run: AgentRun | null) {
  if (!run) return []
  const events = [
    {
      id: `${run.id}-input`,
      icon: MessageSquare,
      tone: "muted" as const,
      label: "User message received",
      meta: formatTime(run.started_at),
      detail: run.input,
    },
    ...run.tool_calls.map((call) => toolEvent(run.id, call)),
    {
      id: `${run.id}-answer`,
      icon: Activity,
      tone: "primary" as const,
      label: "Agent answer completed",
      meta: `${run.latency_ms}ms total`,
      detail: run.final_answer,
    },
    {
      id: `${run.id}-evaluation`,
      icon: run.evaluation_result.passed ? Check : X,
      tone: run.evaluation_result.passed ? ("success" as const) : ("danger" as const),
      label: run.evaluation_result.passed ? "Evaluation passed" : "Evaluation failed",
      meta: `score ${run.evaluation_result.score.toFixed(2)}`,
      detail: run.evaluation_result.failure_reasons.length
        ? run.evaluation_result.failure_reasons.join("; ")
        : "All configured checks passed for this run.",
    },
  ]
  return events
}

function toolEvent(runId: string, call: ToolCall) {
  return {
    id: `${runId}-tool-${call.id}`,
    icon: Wrench,
    tone: call.error ? ("danger" as const) : ("primary" as const),
    label: TOOL_LABELS[call.tool_name] ?? call.tool_name,
    meta: `${call.latency_ms}ms`,
    detail: call.error ?? `Input ${JSON.stringify(call.input)} -> Output ${JSON.stringify(call.output)}`,
  }
}

function TraceStat({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-muted-foreground">
        <Icon className="size-3.5" />
        <span className="font-mono text-[11px] uppercase tracking-wide">{label}</span>
      </div>
      <p className="truncate font-mono text-sm">{value}</p>
    </div>
  )
}

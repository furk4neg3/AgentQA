"use client"

import { useState } from "react"
import { ChevronRight, Search, ShieldCheck, TriangleAlert, Wrench } from "lucide-react"
import { cn } from "@/lib/utils"
import { TOOL_LABELS } from "@/lib/agentqa/seed"
import type { EvaluationResult, RetrievedDocument, ToolCall } from "@/lib/agentqa/types"
import { formatTime } from "./shared"

const METRICS: { key: keyof EvaluationResult; label: string }[] = [
  { key: "tool_call_correctness", label: "Tool-call correctness" },
  { key: "policy_compliance", label: "Policy compliance" },
  { key: "prompt_injection_resistance", label: "Prompt-injection resistance" },
  { key: "groundedness", label: "Groundedness" },
]

function barColor(v: number) {
  if (v >= 0.8) return "bg-success"
  if (v >= 0.5) return "bg-warning"
  return "bg-destructive"
}

export function MetricBars({ evaluation }: { evaluation: EvaluationResult }) {
  return (
    <div className="flex flex-col gap-4">
      {METRICS.map(({ key, label }) => {
        const value = evaluation[key] as number
        return (
          <div key={key}>
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{label}</span>
              <span className="font-mono tabular-nums">{value.toFixed(2)}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full transition-all", barColor(value))}
                style={{ width: `${Math.max(value * 100, 2)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function FailureReasons({ reasons }: { reasons: string[] }) {
  if (!reasons.length) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2.5 text-sm text-success">
        <ShieldCheck className="size-4" />
        All evaluation checks passed.
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {reasons.map((reason, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{reason}</span>
        </div>
      ))}
    </div>
  )
}

export function ToolTrace({ toolCalls }: { toolCalls: ToolCall[] }) {
  if (!toolCalls.length) {
    return (
      <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
        No tools were invoked for this run.
      </p>
    )
  }
  return (
    <ol className="flex flex-col gap-2">
      {toolCalls.map((call, i) => (
        <ToolCallItem key={call.id} call={call} index={i} />
      ))}
    </ol>
  )
}

function ToolCallItem({ call, index }: { call: ToolCall; index: number }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-accent/40"
      >
        <span className="flex size-6 items-center justify-center rounded-md bg-muted font-mono text-xs text-muted-foreground">
          {index + 1}
        </span>
        <Wrench className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm">{TOOL_LABELS[call.tool_name] ?? call.tool_name}</p>
        </div>
        <span className="font-mono text-xs text-muted-foreground">{call.latency_ms}ms</span>
        <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">
          {formatTime(call.started_at)}
        </span>
        <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <div className="grid gap-3 border-t border-border px-3 py-3 sm:grid-cols-2">
          <div>
            <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Input</p>
            <pre className="overflow-x-auto rounded-md bg-muted/60 p-2.5 font-mono text-xs text-foreground">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Output</p>
            <pre className="overflow-x-auto rounded-md bg-muted/60 p-2.5 font-mono text-xs text-foreground">
              {JSON.stringify(call.output, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </li>
  )
}

export function RetrievedDocs({ docs }: { docs: RetrievedDocument[] }) {
  if (!docs.length) {
    return (
      <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
        No policy snippets retrieved.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {docs.map((doc, i) => (
        <div key={`${doc.id}-${i}`} className="rounded-lg border border-border bg-card px-3 py-2.5">
          <div className="mb-1 flex items-center gap-2">
            <Search className="size-3.5 text-primary" />
            <span className="text-sm font-medium">{doc.title}</span>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground">match {doc.score}</span>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">{doc.snippet}</p>
        </div>
      ))}
    </div>
  )
}

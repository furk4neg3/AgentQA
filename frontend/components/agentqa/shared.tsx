import { cn } from "@/lib/utils"
import type { EvaluationOutcome, RunStatus, Severity } from "@/lib/agentqa/types"

export function formatRelativeTime(iso: string): string {
  if (!iso) return "—"
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return "just now"
  if (min < 60) return `${min}m ago`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

export function formatCost(value: number | null): string {
  if (value === null) return "—"
  return value === 0 ? "$0.00" : `$${value.toFixed(6)}`
}

export function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(2)
}

export function formatTokens(value: number | null): string {
  return value === null ? "—" : value.toLocaleString()
}

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: "border-destructive/30 bg-destructive/10 text-destructive",
  high: "border-warning/30 bg-warning/10 text-warning",
  medium: "border-chart-2/30 bg-chart-2/10 text-chart-2",
  low: "border-border bg-muted text-muted-foreground",
  ad_hoc: "border-border bg-muted text-muted-foreground",
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide",
        SEVERITY_STYLES[severity],
        className,
      )}
    >
      {severity}
    </span>
  )
}

export function StatusPill({
  passed,
  outcome,
  status,
  className,
}: {
  passed: boolean | null
  outcome?: EvaluationOutcome
  status?: RunStatus
  className?: string
}) {
  const state =
    status === "running"
      ? { label: "Running", style: "border-chart-2/30 bg-chart-2/10 text-chart-2", dot: "bg-chart-2" }
      : status === "degraded"
        ? { label: "Degraded", style: "border-warning/30 bg-warning/10 text-warning", dot: "bg-warning" }
        : status === "failed" || status === "cancelled"
          ? {
              label: status === "cancelled" ? "Cancelled" : "Failed",
              style: "border-destructive/30 bg-destructive/10 text-destructive",
              dot: "bg-destructive",
            }
          : outcome === "evaluation_error"
            ? {
                label: "Evaluation error",
                style: "border-destructive/30 bg-destructive/10 text-destructive",
                dot: "bg-destructive",
              }
          : outcome === "not_evaluated" || passed === null
            ? { label: "Not evaluated", style: "border-border bg-muted text-muted-foreground", dot: "bg-muted-foreground" }
            : passed
              ? { label: "Pass", style: "border-success/30 bg-success/10 text-success", dot: "bg-success" }
              : { label: "Fail", style: "border-destructive/30 bg-destructive/10 text-destructive", dot: "bg-destructive" }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide",
        state.style,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", state.dot)} />
      {state.label}
    </span>
  )
}

export function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground"
  if (score >= 0.8) return "text-success"
  if (score >= 0.5) return "text-warning"
  return "text-destructive"
}

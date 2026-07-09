import { cn } from "@/lib/utils"
import type { Severity } from "@/lib/agentqa/types"

export function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return "just now"
  if (min < 60) return `${min}m ago`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

export function formatCost(value: number): string {
  return value === 0 ? "$0.00" : `$${value.toFixed(6)}`
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

export function StatusPill({ passed, className }: { passed: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide",
        passed
          ? "border-success/30 bg-success/10 text-success"
          : "border-destructive/30 bg-destructive/10 text-destructive",
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", passed ? "bg-success" : "bg-destructive")} />
      {passed ? "Pass" : "Fail"}
    </span>
  )
}

export function scoreColor(score: number): string {
  if (score >= 0.8) return "text-success"
  if (score >= 0.5) return "text-warning"
  return "text-destructive"
}

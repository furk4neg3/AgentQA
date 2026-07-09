"use client"

import { useMemo } from "react"
import {
  Activity,
  ArrowRight,
  Clock,
  Gauge,
  Play,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  XAxis,
  YAxis,
} from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Button } from "@/components/ui/button"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun } from "@/lib/agentqa/types"
import { formatRelativeTime, scoreColor, SeverityBadge, StatusPill } from "./shared"

interface Props {
  onOpenTrace: (runId: string) => void
  onNavigate: (view: "dashboard" | "runner" | "batch" | "traces" | "settings") => void
}

export function DashboardView({ onOpenTrace, onNavigate }: Props) {
  const { runs, metrics } = useAgentQA()

  const trend = useMemo(() => buildTrend(runs), [runs])
  const radar = useMemo(() => buildRadar(runs), [runs])
  const recent = runs.slice(0, 8)

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Observability</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-balance">Evaluation Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Regression health for the NovaCart Assist support agent.
          </p>
        </div>
        <Button onClick={() => onNavigate("batch")} className="gap-2 self-start sm:self-auto">
          <Play className="size-4" />
          Run Full Suite
        </Button>
      </header>

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          icon={ShieldCheck}
          label="Pass Rate"
          value={`${Math.round(metrics.latest_pass_rate * 100)}%`}
          hint="last 20 runs"
          accent
        />
        <MetricCard
          icon={Activity}
          label="Total Runs"
          value={metrics.total_runs.toString()}
          hint="all time"
        />
        <MetricCard
          icon={TriangleAlert}
          label="Critical Failures"
          value={metrics.critical_failures.toString()}
          hint="severity: critical"
          danger={metrics.critical_failures > 0}
        />
        <MetricCard
          icon={Clock}
          label="Avg Latency"
          value={`${Math.round(metrics.average_latency_ms)}ms`}
          hint="per run"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Pass Rate Over Time</CardTitle>
            <span className="font-mono text-xs text-muted-foreground">score % by run batch</span>
          </CardHeader>
          <CardContent>
            <ChartContainer
              className="h-[220px] w-full"
              config={{
                passRate: { label: "Pass rate", color: "var(--chart-1)" },
              }}
            >
              <AreaChart data={trend} margin={{ left: -16, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="passFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-passRate)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--color-passRate)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  fontSize={11}
                  stroke="var(--muted-foreground)"
                />
                <YAxis
                  domain={[0, 100]}
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  fontSize={11}
                  stroke="var(--muted-foreground)"
                  tickFormatter={(v) => `${v}%`}
                />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area
                  type="monotone"
                  dataKey="passRate"
                  stroke="var(--color-passRate)"
                  strokeWidth={2}
                  fill="url(#passFill)"
                />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Quality Breakdown</CardTitle>
            <Gauge className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <ChartContainer
              className="mx-auto h-[220px] w-full"
              config={{ value: { label: "Avg score", color: "var(--chart-1)" } }}
            >
              <RadarChart data={radar} outerRadius={80}>
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis dataKey="metric" fontSize={10} stroke="var(--muted-foreground)" />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Radar
                  dataKey="value"
                  stroke="var(--color-value)"
                  fill="var(--color-value)"
                  fillOpacity={0.3}
                  strokeWidth={2}
                />
              </RadarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      {/* Recent runs */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Recent Runs</CardTitle>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={() => onNavigate("traces")}>
            View traces
            <ArrowRight className="size-3.5" />
          </Button>
        </CardHeader>
        <CardContent className="px-0">
          <div className="divide-y divide-border">
            {recent.map((run) => (
              <button
                key={run.id}
                onClick={() => onOpenTrace(run.id)}
                className="flex w-full items-center gap-3 px-6 py-3 text-left transition-colors hover:bg-accent/40"
              >
                <StatusPill passed={run.evaluation_result.passed} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{run.scenario_name ?? "Ad-hoc run"}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">{run.input}</p>
                </div>
                <div className="hidden items-center gap-6 sm:flex">
                  <MiniStat label="score" value={run.evaluation_result.score.toFixed(2)} className={scoreColor(run.evaluation_result.score)} />
                  <MiniStat label="latency" value={`${run.latency_ms}ms`} />
                  <SeverityBadge severity={run.evaluation_result.severity} />
                </div>
                <span className="w-16 shrink-0 text-right font-mono text-xs text-muted-foreground">
                  {formatRelativeTime(run.started_at)}
                </span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
  accent,
  danger,
}: {
  icon: typeof Activity
  label: string
  value: string
  hint: string
  accent?: boolean
  danger?: boolean
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
          <Icon
            className={
              danger ? "size-4 text-destructive" : accent ? "size-4 text-primary" : "size-4 text-muted-foreground"
            }
          />
        </div>
        <div>
          <p
            className={
              danger
                ? "text-3xl font-semibold tracking-tight text-destructive"
                : accent
                  ? "text-3xl font-semibold tracking-tight text-primary"
                  : "text-3xl font-semibold tracking-tight"
            }
          >
            {value}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{hint}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function MiniStat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="text-right">
      <p className={`font-mono text-sm ${className ?? ""}`}>{value}</p>
      <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    </div>
  )
}

function buildTrend(runs: AgentRun[]) {
  if (!runs.length) return []
  // Group chronologically into batches of the suite size (~10) for a trend line.
  const chronological = [...runs].sort((a, b) => +new Date(a.started_at) - +new Date(b.started_at))
  const bucketSize = 10
  const points: { label: string; passRate: number }[] = []
  for (let i = 0; i < chronological.length; i += bucketSize) {
    const bucket = chronological.slice(i, i + bucketSize)
    const passed = bucket.filter((r) => r.evaluation_result.passed).length
    points.push({
      label: `#${Math.floor(i / bucketSize) + 1}`,
      passRate: Math.round((passed / bucket.length) * 100),
    })
  }
  return points
}

function buildRadar(runs: AgentRun[]) {
  const dims: [string, keyof AgentRun["evaluation_result"]][] = [
    ["Tools", "tool_call_correctness"],
    ["Policy", "policy_compliance"],
    ["Injection", "prompt_injection_resistance"],
    ["Grounding", "groundedness"],
  ]
  return dims.map(([metric, key]) => {
    const avg = runs.length
      ? runs.reduce((sum, r) => sum + (r.evaluation_result[key] as number), 0) / runs.length
      : 0
    return { metric, value: Math.round(avg * 100) }
  })
}

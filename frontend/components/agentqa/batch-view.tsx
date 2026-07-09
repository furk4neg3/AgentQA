"use client"

import { useState } from "react"
import { Layers, Loader, Play } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun } from "@/lib/agentqa/types"
import { scoreColor, SeverityBadge, StatusPill } from "./shared"

interface BatchState {
  results: AgentRun[]
  average_score: number
  pass_rate: number
}

export function BatchView({ onOpenTrace }: { onOpenTrace: (id: string) => void }) {
  const { scenarios, hydrated, runBatch } = useAgentQA()
  const [running, setRunning] = useState(false)
  const [batch, setBatch] = useState<BatchState | null>(null)

  const handleRun = async () => {
    setRunning(true)
    try {
      const result = await runBatch()
      setBatch(result)
      toast.success("Batch evaluation complete", {
        description: `${Math.round(result.pass_rate * 100)}% pass rate across ${result.results.length} scenarios`,
      })
    } catch (error) {
      toast.error("Batch evaluation failed", {
        description: error instanceof Error ? error.message : "Could not run suite",
      })
    } finally {
      setRunning(false)
    }
  }

  const passed = batch?.results.filter((r) => r.evaluation_result.passed).length ?? 0
  const failed = (batch?.results.length ?? 0) - passed

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Regression</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Batch Evaluation</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Run all {scenarios.length} seeded scenarios and review the regression summary.
          </p>
        </div>
        <Button onClick={handleRun} disabled={running || !hydrated} className="gap-2 self-start sm:self-auto">
          {running ? <Loader className="size-4 animate-spin" /> : <Play className="size-4" />}
          {running ? "Evaluating suite..." : "Run All Scenarios"}
        </Button>
      </header>

      {!batch ? (
        <Card className="flex items-center justify-center border-dashed">
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Layers className="size-5 text-muted-foreground" />
            </div>
            <p className="max-w-sm text-sm text-muted-foreground">
              Launch the full suite to measure pass rate, average score, and per-scenario results in one pass.
            </p>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <SummaryCard label="Pass Rate" value={`${Math.round(batch.pass_rate * 100)}%`} accent />
            <SummaryCard label="Avg Score" value={batch.average_score.toFixed(2)} />
            <SummaryCard label="Passed" value={passed.toString()} tone="success" />
            <SummaryCard label="Failed" value={failed.toString()} tone={failed ? "danger" : undefined} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Scenario Results</CardTitle>
            </CardHeader>
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
                      <TableHead className="pr-6">Failure reasons</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {batch.results.map((run) => (
                      <TableRow
                        key={run.id}
                        className="cursor-pointer"
                        onClick={() => onOpenTrace(run.id)}
                      >
                        <TableCell className="pl-6">
                          <StatusPill passed={run.evaluation_result.passed} />
                        </TableCell>
                        <TableCell className="max-w-56">
                          <p className="truncate text-sm font-medium">{run.scenario_name ?? "Ad-hoc run"}</p>
                          <p className="truncate font-mono text-xs text-muted-foreground">{run.input}</p>
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono ${scoreColor(run.evaluation_result.score)}`}
                        >
                          {run.evaluation_result.score.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm text-muted-foreground">
                          {run.latency_ms}ms
                        </TableCell>
                        <TableCell>
                          <SeverityBadge severity={run.evaluation_result.severity} />
                        </TableCell>
                        <TableCell className="max-w-64 pr-6">
                          {run.evaluation_result.failure_reasons.length ? (
                            <span className="line-clamp-2 text-xs text-destructive">
                              {run.evaluation_result.failure_reasons.join("; ")}
                            </span>
                          ) : (
                            <span className="font-mono text-xs text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      </TableRow>
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

function SummaryCard({
  label,
  value,
  accent,
  tone,
}: {
  label: string
  value: string
  accent?: boolean
  tone?: "success" | "danger"
}) {
  const valueClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "success"
        ? "text-success"
        : accent
          ? "text-primary"
          : "text-foreground"
  return (
    <Card>
      <CardContent className="p-4">
        <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-2 text-3xl font-semibold tracking-tight ${valueClass}`}>{value}</p>
      </CardContent>
    </Card>
  )
}

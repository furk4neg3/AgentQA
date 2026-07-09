"use client"

import { useEffect, useState } from "react"
import { Clock, Cpu, DollarSign, Gauge, Loader, Play, ScrollText, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun, Scenario } from "@/lib/agentqa/types"
import { formatCost, scoreColor, SeverityBadge, StatusPill } from "./shared"
import { FailureReasons, MetricBars, RetrievedDocs, ToolTrace } from "./evaluation-panels"

export function RunnerView({ onOpenTrace }: { onOpenTrace: (id: string) => void }) {
  const { scenarios, hydrated, runOnce } = useAgentQA()
  const [scenarioId, setScenarioId] = useState<string>(scenarios[0].id)
  const [input, setInput] = useState<string>(scenarios[0].input)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentRun | null>(null)

  const selected: Scenario = scenarios.find((s) => s.id === scenarioId) ?? scenarios[0]

  useEffect(() => {
    if (scenarios.some((scenario) => scenario.id === scenarioId)) return
    const firstScenario = scenarios[0]
    if (!firstScenario) return
    setScenarioId(firstScenario.id)
    setInput(firstScenario.input)
  }, [scenarioId, scenarios])

  const onSelectScenario = (id: string | null) => {
    if (!id) return
    setScenarioId(id)
    const scenario = scenarios.find((s) => s.id === id)
    if (scenario) setInput(scenario.input)
  }

  const handleRun = async () => {
    if (!input.trim()) return
    setRunning(true)
    try {
      const run = await runOnce(scenarioId, input)
      setResult(run)
      toast[run.evaluation_result.passed ? "success" : "error"](
        run.evaluation_result.passed ? "Scenario passed" : "Scenario failed",
        { description: `Score ${run.evaluation_result.score.toFixed(2)} · ${run.latency_ms}ms` },
      )
    } catch (error) {
      toast.error("Scenario run failed", {
        description: error instanceof Error ? error.message : "Could not create run",
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Interactive</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Scenario Runner</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Execute a single scenario against the agent and inspect the evaluation.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Config panel */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Test Input</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="scenario">Scenario</Label>
              <Select value={scenarioId} onValueChange={onSelectScenario}>
                <SelectTrigger id="scenario">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {scenarios.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="input">User message</Label>
              <Textarea
                id="input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={4}
                className="resize-none font-mono text-sm"
              />
            </div>

            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                  Expected behavior
                </span>
                <SeverityBadge severity={selected.severity} />
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">{selected.expected_behavior}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {selected.expected_tools.length ? (
                  selected.expected_tools.map((t) => (
                    <span
                      key={t}
                      className="rounded-md border border-border bg-card px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {t}
                    </span>
                  ))
                ) : (
                  <span className="font-mono text-[11px] text-muted-foreground">no tools expected</span>
                )}
              </div>
            </div>

            <Button onClick={handleRun} disabled={running || !hydrated} className="gap-2">
              {running ? <Loader className="size-4 animate-spin" /> : <Play className="size-4" />}
              {running ? "Running agent..." : "Run Scenario"}
            </Button>
          </CardContent>
        </Card>

        {/* Result panel */}
        <div className="lg:col-span-3">
          {!result ? (
            <Card className="flex h-full min-h-80 items-center justify-center border-dashed">
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <div className="flex size-12 items-center justify-center rounded-full bg-muted">
                  <Sparkles className="size-5 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Run a scenario to see the evaluation report.</p>
              </div>
            </Card>
          ) : (
            <div className="flex flex-col gap-4">
              <Card>
                <CardContent className="flex flex-col gap-4 p-5">
                  <div className="flex items-center justify-between">
                    <StatusPill passed={result.evaluation_result.passed} />
                    <span className={`font-mono text-2xl font-semibold ${scoreColor(result.evaluation_result.score)}`}>
                      {result.evaluation_result.score.toFixed(2)}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <ResultStat icon={Clock} label="Latency" value={`${result.latency_ms}ms`} />
                    <ResultStat icon={DollarSign} label="Cost" value={formatCost(result.estimated_cost_usd)} />
                    <ResultStat icon={Cpu} label="Model" value={result.model_provider} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Final Answer</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-pretty">{result.final_answer}</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-base">Evaluation Metrics</CardTitle>
                  <Gauge className="size-4 text-muted-foreground" />
                </CardHeader>
                <CardContent className="flex flex-col gap-5">
                  <MetricBars evaluation={result.evaluation_result} />
                  <FailureReasons reasons={result.evaluation_result.failure_reasons} />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Tool Calls</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <ToolTrace toolCalls={result.tool_calls} />
                  <RetrievedDocs docs={result.retrieved_documents} />
                </CardContent>
              </Card>

              <Button variant="outline" className="gap-2" onClick={() => onOpenTrace(result.id)}>
                <ScrollText className="size-4" />
                Open in Trace Viewer
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ResultStat({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
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

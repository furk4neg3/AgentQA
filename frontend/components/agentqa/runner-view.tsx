"use client"

import { useMemo, useState } from "react"
import { Clock, Coins, Cpu, Gauge, Loader, Play, ScrollText, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { buildRunRequest } from "@/lib/agentqa/run-mode"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentRun, RunMode, Scenario } from "@/lib/agentqa/types"
import { formatCost, formatScore, formatTokens, scoreColor, SeverityBadge, StatusPill } from "./shared"
import { EvaluationChecks, FailureReasons, MetricBars, RetrievedDocs, ToolTrace } from "./evaluation-panels"

const RUN_MODES: { value: RunMode; label: string }[] = [
  { value: "scenario", label: "Stored scenario" },
  { value: "mutation", label: "Mutation" },
  { value: "ad_hoc", label: "Ad hoc" },
]

export function RunnerView({ onOpenTrace }: { onOpenTrace: (id: string) => void }) {
  const { scenarios, hydrated, runOnce } = useAgentQA()
  const [mode, setMode] = useState<RunMode>("scenario")
  const [scenarioId, setScenarioId] = useState("")
  const [evaluationSpecId, setEvaluationSpecId] = useState<string>("none")
  const [input, setInput] = useState("")
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentRun | null>(null)

  const resolvedScenarioId = scenarioId || scenarios[0]?.id || ""
  const selected = useMemo(
    () => scenarios.find((scenario) => scenario.id === resolvedScenarioId) ?? null,
    [resolvedScenarioId, scenarios],
  )

  const onSelectScenario = (id: string | null) => {
    if (!id) return
    setScenarioId(id)
    const scenario = scenarios.find((item) => item.id === id)
    if (scenario) setInput(scenario.input)
  }

  const onSelectMode = (next: string | null) => {
    if (!next) return
    const nextMode = next as RunMode
    setMode(nextMode)
    setInput(nextMode === "ad_hoc" ? "" : (selected?.input ?? ""))
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      const payload = buildRunRequest(
        mode,
        mode === "ad_hoc" ? null : resolvedScenarioId,
        input,
        mode === "ad_hoc" && evaluationSpecId !== "none" ? evaluationSpecId : null,
      )
      const run = await runOnce(payload)
      setResult(run)
      const evaluation = run.evaluation_result
      if (run.status === "failed") {
        toast.error("Provider run failed", { description: run.provider_error?.message ?? "The provider did not return an answer." })
      } else if (evaluation.outcome === "not_evaluated") {
        toast.info("Run completed — not evaluated", { description: `${run.latency_ms}ms` })
      } else {
        toast[evaluation.passed ? "success" : "error"](
          evaluation.passed ? "Scenario passed" : "Scenario failed",
          { description: `Score ${formatScore(evaluation.score)} · ${run.latency_ms}ms` },
        )
      }
    } catch (error) {
      toast.error("Scenario run failed", {
        description: error instanceof Error ? error.message : "Could not create run",
      })
    } finally {
      setRunning(false)
    }
  }

  const expectedTools = selected?.expected_tools ?? []
  const cannotRun = !hydrated || running || (mode !== "ad_hoc" && !selected) || (mode !== "scenario" && !input.trim())

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Interactive</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Scenario Runner</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Execute a stored case, an explicit mutation, or an ad-hoc request against the agent.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Test Input</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="run-mode">Execution mode</Label>
              <Select value={mode} onValueChange={onSelectMode}>
                <SelectTrigger id="run-mode" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RUN_MODES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {mode === "scenario" && "Uses the immutable stored input and its evaluation specification."}
                {mode === "mutation" && "Evaluates your edited input against the selected scenario specification."}
                {mode === "ad_hoc" && "Runs free-form input. It is Not evaluated unless you select a specification."}
              </p>
            </div>

            {mode !== "ad_hoc" && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="scenario">Scenario</Label>
                <Select value={resolvedScenarioId || null} onValueChange={onSelectScenario}>
                  <SelectTrigger id="scenario" className="w-full">
                    <SelectValue placeholder="Select a scenario" />
                  </SelectTrigger>
                  <SelectContent>
                    {scenarios.map((scenario) => (
                      <SelectItem key={scenario.id} value={scenario.id}>
                        {scenario.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {mode === "ad_hoc" && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="evaluation-spec">Evaluation specification</Label>
                <Select value={evaluationSpecId} onValueChange={(value) => value && setEvaluationSpecId(value)}>
                  <SelectTrigger id="evaluation-spec" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None — Not evaluated</SelectItem>
                    {scenarios.map((scenario) => (
                      <SelectItem key={scenario.id} value={scenario.id}>
                        {scenario.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <Label htmlFor="input">User message</Label>
              <Textarea
                id="input"
                value={mode === "scenario" ? (selected?.input ?? "") : input}
                onChange={(event) => setInput(event.target.value)}
                readOnly={mode === "scenario"}
                aria-describedby="input-mode-description"
                rows={4}
                className="resize-none font-mono text-sm read-only:cursor-default read-only:opacity-80"
              />
              <p id="input-mode-description" className="sr-only">
                {mode === "scenario" ? "Stored scenario input is read only." : "Enter the input to send to the agent."}
              </p>
            </div>

            {selected && mode !== "ad_hoc" && (
              <ScenarioExpectation scenario={selected} expectedTools={expectedTools} />
            )}

            <Button onClick={handleRun} disabled={cannotRun} className="gap-2">
              {running ? <Loader className="size-4 animate-spin" /> : <Play className="size-4" />}
              {running ? "Running agent..." : mode === "scenario" ? "Run Scenario" : "Run Input"}
            </Button>
          </CardContent>
        </Card>

        <div className="lg:col-span-3">
          {!result ? (
            <Card className="flex h-full min-h-80 items-center justify-center border-dashed">
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <div className="flex size-12 items-center justify-center rounded-full bg-muted">
                  <Sparkles className="size-5 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">Run an input to see its provider and evaluation report.</p>
              </div>
            </Card>
          ) : (
            <RunResult result={result} onOpenTrace={onOpenTrace} />
          )}
        </div>
      </div>
    </div>
  )
}

function ScenarioExpectation({ scenario, expectedTools }: { scenario: Scenario; expectedTools: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Expected behavior</span>
        <SeverityBadge severity={scenario.severity} />
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{scenario.expected_behavior}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {expectedTools.length ? (
          expectedTools.map((tool) => (
            <span key={tool} className="rounded-md border border-border bg-card px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {tool}
            </span>
          ))
        ) : (
          <span className="font-mono text-[11px] text-muted-foreground">no tools expected</span>
        )}
      </div>
    </div>
  )
}

function RunResult({ result, onOpenTrace }: { result: AgentRun; onOpenTrace: (id: string) => void }) {
  const evaluation = result.evaluation_result
  return (
    <div className="flex flex-col gap-4" aria-live="polite">
      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex items-center justify-between">
            <StatusPill passed={evaluation.passed} outcome={evaluation.outcome} status={result.status} />
            <span className={`font-mono text-2xl font-semibold ${scoreColor(evaluation.score)}`}>
              {formatScore(evaluation.score)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ResultStat icon={Clock} label="Latency" value={`${result.latency_ms}ms`} />
            <ResultStat icon={Coins} label="Cost" value={formatCost(result.cost_usd)} />
            <ResultStat icon={Cpu} label="Provider" value={result.model_provider} />
            <ResultStat icon={Gauge} label="Tokens" value={formatTokens(result.usage.total_tokens)} />
          </div>
          {(result.provider_error || result.fallback_reason) && (
            <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm text-warning">
              {result.provider_error && <p>Provider error ({result.provider_error.category}): {result.provider_error.message}</p>}
              {result.fallback_reason && <p>Fallback reason: {result.fallback_reason}</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Final Answer</CardTitle></CardHeader>
        <CardContent><p className="text-sm leading-relaxed text-pretty">{result.final_answer || "No final answer was produced."}</p></CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Evaluation</CardTitle>
          <Gauge className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {evaluation.outcome === "not_evaluated" ? (
            <p className="rounded-lg border border-border bg-muted/40 px-3 py-3 text-sm text-muted-foreground">
              Not evaluated. Run again with an evaluation specification to receive a score.
            </p>
          ) : (
            <>
              <MetricBars evaluation={evaluation} />
              <EvaluationChecks checks={evaluation.checks} />
              <FailureReasons reasons={evaluation.failure_reasons} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Tool Calls</CardTitle></CardHeader>
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

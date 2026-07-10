"use client"

import { useCallback, useEffect, useState } from "react"
import { Archive, Copy, Download, FileUp, Pencil, Plus, RotateCcw, Save, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  createScenario,
  createSuite,
  deleteScenario,
  deleteSuite,
  duplicateScenario,
  exportScenarios,
  importScenarios,
  listScenarios,
  listSuites,
  setScenarioArchived,
  setSuiteArchived,
  updateScenario,
  updateSuite,
} from "@/lib/agentqa/api"
import { useAgentQA } from "@/lib/agentqa/store"
import type { Scenario, ScenarioWrite, Severity, Suite, SuiteWrite } from "@/lib/agentqa/types"
import { SeverityBadge } from "./shared"

const DEFAULT_SPEC: Record<string, unknown> = {
  schema_version: "1.0",
  minimum_passing_score: 0.8,
  checks: [
    {
      type: "no_tool_errors",
      check_id: "no-tool-errors",
      label: "Tools complete without errors",
      dimension: "tool_call_correctness",
      weight: 1,
      hard_failure: true,
    },
  ],
}

const EMPTY_SCENARIO: ScenarioWrite = {
  id: "",
  name: "",
  input: "",
  expected_behavior: "",
  severity: "medium",
  evaluation_spec: DEFAULT_SPEC,
  evaluation_spec_version: "1.0",
  expected_tools: [],
  must_not_include: [],
}

const EMPTY_SUITE: SuiteWrite = { name: "", description: "", scenario_ids: [] }

export function LibraryView() {
  const { refresh } = useAgentQA()
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [suites, setSuites] = useState<Suite[]>([])
  const [includeArchived, setIncludeArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextScenarios, nextSuites] = await Promise.all([
        listScenarios({ includeArchived }),
        listSuites(includeArchived),
      ])
      setScenarios(nextScenarios)
      setSuites(nextSuites)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the scenario library")
    } finally {
      setLoading(false)
    }
  }, [includeArchived])

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0)
    return () => clearTimeout(timer)
  }, [load])

  const reloadWorkspace = async () => {
    await load()
    await refresh()
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Test assets</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Scenario Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">Maintain versioned evaluation scenarios and group them into reusable suites.</p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
            className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          />
          Include archived
        </label>
      </header>

      {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <Tabs defaultValue="scenarios">
        <TabsList aria-label="Scenario library sections">
          <TabsTrigger value="scenarios">Scenarios ({scenarios.length})</TabsTrigger>
          <TabsTrigger value="suites">Suites ({suites.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="scenarios" className="mt-4">
          <ScenarioManager scenarios={scenarios} loading={loading} reload={reloadWorkspace} />
        </TabsContent>
        <TabsContent value="suites" className="mt-4">
          <SuiteManager scenarios={scenarios} suites={suites} loading={loading} reload={reloadWorkspace} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function ScenarioManager({ scenarios, loading, reload }: { scenarios: Scenario[]; loading: boolean; reload: () => Promise<void> }) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<ScenarioWrite | null>(null)
  const [specText, setSpecText] = useState("")
  const [saving, setSaving] = useState(false)

  const startCreate = () => {
    setEditingId(null)
    setDraft({ ...EMPTY_SCENARIO, evaluation_spec: { ...DEFAULT_SPEC } })
    setSpecText(JSON.stringify(DEFAULT_SPEC, null, 2))
  }

  const startEdit = (scenario: Scenario) => {
    setEditingId(scenario.id)
    setDraft({
      id: scenario.id,
      name: scenario.name,
      input: scenario.input,
      expected_behavior: scenario.expected_behavior,
      severity: scenario.severity,
      evaluation_spec: scenario.evaluation_spec ?? DEFAULT_SPEC,
      evaluation_spec_version: scenario.evaluation_spec_version ?? "1.0",
      expected_tools: scenario.expected_tools ?? [],
      must_not_include: scenario.must_not_include ?? [],
    })
    setSpecText(JSON.stringify(scenario.evaluation_spec ?? DEFAULT_SPEC, null, 2))
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const evaluationSpec = JSON.parse(specText) as Record<string, unknown>
      const payload = { ...draft, evaluation_spec: evaluationSpec }
      if (editingId) {
        const { id: scenarioId, ...updates } = payload
        await updateScenario(scenarioId, updates)
      } else {
        await createScenario(payload)
      }
      toast.success(editingId ? "Scenario updated" : "Scenario created")
      setDraft(null)
      await reload()
    } catch (caught) {
      toast.error("Could not save scenario", { description: caught instanceof Error ? caught.message : "Invalid scenario" })
    } finally {
      setSaving(false)
    }
  }

  const mutate = async (action: () => Promise<unknown>, success: string) => {
    try {
      await action()
      toast.success(success)
      await reload()
    } catch (caught) {
      toast.error("Scenario action failed", { description: caught instanceof Error ? caught.message : "Request failed" })
    }
  }

  const exportJson = async () => {
    try {
      downloadJson("agentqa-scenarios.json", await exportScenarios())
      toast.success("Scenario JSON exported")
    } catch (caught) {
      toast.error("Could not export scenarios", { description: caught instanceof Error ? caught.message : "Request failed" })
    }
  }

  const importJson = async (file: File | undefined) => {
    if (!file) return
    try {
      const parsed = JSON.parse(await file.text()) as { scenarios?: ScenarioWrite[] }
      if (!Array.isArray(parsed.scenarios)) throw new Error("JSON must contain a scenarios array.")
      const result = await importScenarios({ scenarios: parsed.scenarios, replace_existing: false })
      toast.success(`Imported ${result.imported} scenario${result.imported === 1 ? "" : "s"}`)
      await reload()
    } catch (caught) {
      toast.error("Could not import scenarios", { description: caught instanceof Error ? caught.message : "Invalid JSON file" })
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-base">Scenarios</CardTitle>
          <div className="flex flex-wrap gap-2">
            <input id="scenario-import" type="file" accept="application/json,.json" className="sr-only" onChange={(event) => void importJson(event.target.files?.[0])} />
            <Button render={<label htmlFor="scenario-import" />} variant="outline" size="sm" className="cursor-pointer gap-1.5"><FileUp className="size-3.5" /> Import</Button>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={exportJson}><Download className="size-3.5" /> Export</Button>
            <Button size="sm" className="gap-1.5" onClick={startCreate}><Plus className="size-3.5" /> New</Button>
          </div>
        </CardHeader>
        <CardContent className="flex max-h-[650px] flex-col gap-2 overflow-y-auto">
          {loading && <p className="py-6 text-center text-sm text-muted-foreground">Loading scenarios…</p>}
          {!loading && !scenarios.length && <p className="py-6 text-center text-sm text-muted-foreground">No scenarios found.</p>}
          {scenarios.map((scenario) => (
            <div key={scenario.id} className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><p className="truncate text-sm font-medium">{scenario.name}</p><SeverityBadge severity={scenario.severity} />{scenario.archived_at && <span className="font-mono text-[10px] uppercase text-warning">Archived</span>}</div>
                  <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{scenario.id}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <IconButton label={`Edit ${scenario.name}`} onClick={() => startEdit(scenario)}><Pencil /></IconButton>
                  <IconButton label={`Duplicate ${scenario.name}`} onClick={() => void mutate(() => duplicateScenario(scenario.id), "Scenario duplicated")}><Copy /></IconButton>
                  <IconButton label={`${scenario.archived_at ? "Restore" : "Archive"} ${scenario.name}`} onClick={() => void mutate(() => setScenarioArchived(scenario.id, !scenario.archived_at), scenario.archived_at ? "Scenario restored" : "Scenario archived")}>
                    {scenario.archived_at ? <RotateCcw /> : <Archive />}
                  </IconButton>
                  <IconButton label={`Delete ${scenario.name}`} destructive onClick={() => { if (window.confirm(`Delete scenario “${scenario.name}”?`)) void mutate(() => deleteScenario(scenario.id), "Scenario deleted") }}><Trash2 /></IconButton>
                </div>
              </div>
              <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{scenario.expected_behavior}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">{draft ? (editingId ? "Edit scenario" : "Create scenario") : "Scenario editor"}</CardTitle></CardHeader>
        <CardContent>
          {!draft ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-12 text-center text-sm text-muted-foreground">Select a scenario to edit, or create a new one.</p>
          ) : (
            <div className="flex flex-col gap-4">
              <Field label="Scenario ID" id="scenario-id"><Input id="scenario-id" value={draft.id} readOnly={Boolean(editingId)} onChange={(event) => setDraft({ ...draft, id: event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-") })} /></Field>
              <Field label="Name" id="scenario-name"><Input id="scenario-name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
              <Field label="User input" id="scenario-input"><Textarea id="scenario-input" rows={3} value={draft.input} onChange={(event) => setDraft({ ...draft, input: event.target.value })} /></Field>
              <Field label="Expected behavior" id="scenario-behavior"><Textarea id="scenario-behavior" rows={3} value={draft.expected_behavior} onChange={(event) => setDraft({ ...draft, expected_behavior: event.target.value })} /></Field>
              <Field label="Severity" id="scenario-severity">
                <Select value={draft.severity} onValueChange={(value) => value && setDraft({ ...draft, severity: value as Severity })}>
                  <SelectTrigger id="scenario-severity" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{(["low", "medium", "high", "critical"] as Severity[]).map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="Evaluation specification (JSON)" id="scenario-spec"><Textarea id="scenario-spec" rows={12} className="font-mono text-xs" value={specText} onChange={(event) => setSpecText(event.target.value)} /></Field>
              <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setDraft(null)}>Cancel</Button><Button className="gap-1.5" disabled={saving} onClick={save}><Save className="size-3.5" /> {saving ? "Saving…" : "Save scenario"}</Button></div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function SuiteManager({ scenarios, suites, loading, reload }: { scenarios: Scenario[]; suites: Suite[]; loading: boolean; reload: () => Promise<void> }) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<SuiteWrite | null>(null)

  const edit = (suite: Suite) => { setEditingId(suite.id); setDraft({ name: suite.name, description: suite.description, scenario_ids: suite.scenario_ids }) }
  const save = async () => {
    if (!draft) return
    try {
      if (editingId) await updateSuite(editingId, draft)
      else await createSuite(draft)
      toast.success(editingId ? "Suite updated" : "Suite created")
      setDraft(null)
      await reload()
    } catch (caught) {
      toast.error("Could not save suite", { description: caught instanceof Error ? caught.message : "Request failed" })
    }
  }
  const mutate = async (action: () => Promise<unknown>, success: string) => {
    try { await action(); toast.success(success); await reload() }
    catch (caught) { toast.error("Suite action failed", { description: caught instanceof Error ? caught.message : "Request failed" }) }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base">Suites</CardTitle><Button size="sm" className="gap-1.5" onClick={() => { setEditingId(null); setDraft({ ...EMPTY_SUITE }) }}><Plus className="size-3.5" /> New</Button></CardHeader>
        <CardContent className="flex flex-col gap-2">
          {loading && <p className="py-6 text-center text-sm text-muted-foreground">Loading suites…</p>}
          {!loading && !suites.length && <p className="py-6 text-center text-sm text-muted-foreground">No suites found.</p>}
          {suites.map((suite) => (
            <div key={suite.id} className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium">{suite.name}</p><p className="mt-1 text-xs text-muted-foreground">{suite.scenario_ids.length} scenarios{suite.baseline_batch_id ? " · baseline selected" : ""}</p></div><div className="flex gap-1"><IconButton label={`Edit ${suite.name}`} onClick={() => edit(suite)}><Pencil /></IconButton><IconButton label={`${suite.archived_at ? "Restore" : "Archive"} ${suite.name}`} onClick={() => void mutate(() => setSuiteArchived(suite.id, !suite.archived_at), suite.archived_at ? "Suite restored" : "Suite archived")}>{suite.archived_at ? <RotateCcw /> : <Archive />}</IconButton><IconButton destructive label={`Delete ${suite.name}`} onClick={() => { if (window.confirm(`Delete suite “${suite.name}”?`)) void mutate(() => deleteSuite(suite.id), "Suite deleted") }}><Trash2 /></IconButton></div></div>
              {suite.description && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{suite.description}</p>}
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">{draft ? (editingId ? "Edit suite" : "Create suite") : "Suite editor"}</CardTitle></CardHeader>
        <CardContent>
          {!draft ? <p className="rounded-lg border border-dashed border-border px-4 py-12 text-center text-sm text-muted-foreground">Select a suite to edit, or create a new one.</p> : (
            <div className="flex flex-col gap-4">
              <Field label="Name" id="suite-name"><Input id="suite-name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
              <Field label="Description" id="suite-description"><Textarea id="suite-description" rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field>
              <fieldset><legend className="mb-2 text-sm font-medium">Scenarios</legend><div className="grid max-h-72 gap-2 overflow-y-auto sm:grid-cols-2">{scenarios.filter((scenario) => !scenario.archived_at).map((scenario) => <label key={scenario.id} className="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-2 text-sm"><input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={draft.scenario_ids.includes(scenario.id)} onChange={() => setDraft({ ...draft, scenario_ids: draft.scenario_ids.includes(scenario.id) ? draft.scenario_ids.filter((id) => id !== scenario.id) : [...draft.scenario_ids, scenario.id] })} /><span>{scenario.name}</span></label>)}</div></fieldset>
              <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setDraft(null)}>Cancel</Button><Button className="gap-1.5" onClick={save}><Save className="size-3.5" /> Save suite</Button></div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div className="flex flex-col gap-2"><Label htmlFor={id}>{label}</Label>{children}</div>
}

function IconButton({ label, destructive, onClick, children }: { label: string; destructive?: boolean; onClick: () => void; children: React.ReactNode }) {
  return <Button type="button" variant={destructive ? "destructive" : "ghost"} size="icon-sm" aria-label={label} onClick={onClick}>{children}</Button>
}

function downloadJson(filename: string, payload: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

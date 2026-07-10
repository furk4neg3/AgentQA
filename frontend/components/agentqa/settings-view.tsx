"use client"

import { useMemo, useState } from "react"
import {
  AlertCircle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Gauge,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Wrench,
} from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Slider } from "@/components/ui/slider"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { cn } from "@/lib/utils"
import { useAgentQA } from "@/lib/agentqa/store"
import type { AgentConfig } from "@/lib/agentqa/types"

const MODES: { value: AgentConfig["model_mode"]; label: string; desc: string }[] = [
  { value: "mock", label: "Mock", desc: "Deterministic rule-based agent. Zero cost, ideal for regression." },
  { value: "gemini", label: "Gemini", desc: "Gemini function calling with validated, allowlisted NovaCart tools." },
]

const SETTINGS_FIELDS = [
  "agent_name",
  "system_prompt",
  "model_mode",
  "model_name",
  "temperature",
  "max_tool_calls",
  "request_timeout_seconds",
  "max_retries",
  "fallback_enabled",
] as const

type SettingsField = (typeof SETTINGS_FIELDS)[number]

type Preset = {
  id: string
  label: string
  desc: string
  icon: typeof ShieldCheck
  patch: Partial<Pick<AgentConfig, SettingsField>>
}

export function SettingsView() {
  const { config, updateConfig } = useAgentQA()
  const [draft, setDraft] = useState<AgentConfig>(config)
  const [saving, setSaving] = useState(false)
  const presets = useMemo(() => createPresets(config), [config])

  const dirty = SETTINGS_FIELDS.some((field) => draft[field] !== config[field])
  const validationErrors = useMemo(() => validateDraft(draft), [draft])
  const canSave = dirty && validationErrors.length === 0
  const activePreset = useMemo(() => findActivePreset(draft, presets), [draft, presets])

  const set = <K extends keyof AgentConfig>(key: K, value: AgentConfig[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }))

  const applyPreset = (preset: Preset) => {
    setDraft((prev) => ({ ...prev, ...preset.patch }))
    toast.message(`${preset.label} preset applied`, { description: "Save to use it for new runs." })
  }

  const handleSave = async () => {
    if (validationErrors.length) {
      toast.error("Fix settings before saving", { description: validationErrors[0] })
      return
    }
    setSaving(true)
    try {
      const updated = await updateConfig({
        agent_name: draft.agent_name,
        system_prompt: draft.system_prompt,
        model_mode: draft.model_mode,
        temperature: draft.temperature,
        max_tool_calls: draft.max_tool_calls,
        model_name: draft.model_name,
        request_timeout_seconds: draft.request_timeout_seconds,
        max_retries: draft.max_retries,
        fallback_enabled: draft.fallback_enabled,
      })
      setDraft(updated)
      toast.success("Agent settings saved", { description: "New runs will use the updated configuration." })
    } catch (error) {
      toast.error("Could not save settings", {
        description: error instanceof Error ? error.message : "Backend update failed",
      })
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    setDraft(config)
    toast.message("Unsaved changes discarded")
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Configuration</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Agent Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Tune the agent identity, prompt, and evaluation guardrails.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button variant="outline" className="gap-2" onClick={handleReset}>
            <RefreshCw className="size-4" />
            Discard changes
          </Button>
          <Button className="gap-2" onClick={handleSave} disabled={!canSave || saving}>
            <Save className="size-4" />
            {saving ? "Saving..." : "Save Settings"}
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Presets</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {presets.map((preset) => (
                <button
                  type="button"
                  key={preset.id}
                  onClick={() => applyPreset(preset)}
                  aria-pressed={activePreset === preset.id}
                  className={cn(
                    "flex min-h-32 flex-col items-start gap-3 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    activePreset === preset.id
                      ? "border-primary/50 bg-primary/10"
                      : "border-border bg-muted/20 hover:bg-accent/30",
                  )}
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <preset.icon className="size-4 text-primary" />
                    {activePreset === preset.id && <CheckCircle2 className="size-4 text-success" />}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{preset.label}</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{preset.desc}</p>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Identity & Prompt</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="agent-name">Agent name</Label>
                <Input
                  id="agent-name"
                  value={draft.agent_name}
                  maxLength={120}
                  onChange={(e) => set("agent_name", e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="system-prompt">System prompt</Label>
                  <span
                    className={cn(
                      "font-mono text-[11px]",
                      draft.system_prompt.trim().length < 20 ? "text-destructive" : "text-muted-foreground",
                    )}
                  >
                    {draft.system_prompt.trim().length} chars
                  </span>
                </div>
                <Textarea
                  id="system-prompt"
                  value={draft.system_prompt}
                  onChange={(e) => set("system_prompt", e.target.value)}
                  rows={7}
                  className="resize-none font-mono text-sm leading-relaxed"
                />
                <PromptHealth prompt={draft.system_prompt} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Model Mode</CardTitle>
            </CardHeader>
            <CardContent>
              <RadioGroup
                value={draft.model_mode}
                onValueChange={(v) => set("model_mode", v as AgentConfig["model_mode"])}
                className="grid grid-cols-1 gap-3 sm:grid-cols-2"
              >
                {MODES.map((mode) => (
                  <Label
                    key={mode.value}
                    htmlFor={`mode-${mode.value}`}
                    className={cn(
                      "flex cursor-pointer flex-col gap-2 rounded-lg border p-4 transition-colors",
                      draft.model_mode === mode.value
                        ? "border-primary/50 bg-accent/40"
                        : "border-border hover:bg-accent/20",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <RadioGroupItem id={`mode-${mode.value}`} value={mode.value} />
                      <span className="text-sm font-medium">{mode.label}</span>
                    </div>
                    <span className="text-xs leading-relaxed text-muted-foreground">{mode.desc}</span>
                  </Label>
                ))}
              </RadioGroup>
              <div className="mt-4 flex flex-col gap-2">
                <Label htmlFor="model-name">Model name override</Label>
                <Input
                  id="model-name"
                  value={draft.model_name ?? ""}
                  placeholder="Use provider default"
                  onChange={(event) => set("model_name", event.target.value || null)}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Config Health</CardTitle>
              {validationErrors.length ? (
                <AlertCircle className="size-4 text-destructive" />
              ) : (
                <CheckCircle2 className="size-4 text-success" />
              )}
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <HealthRow
                ok={draft.agent_name.trim().length >= 2}
                label="Agent name"
                detail={draft.agent_name.trim().length >= 2 ? "Ready" : "Use at least 2 characters"}
              />
              <HealthRow
                ok={draft.system_prompt.trim().length >= 20}
                label="System prompt"
                detail={draft.system_prompt.trim().length >= 20 ? "Minimum context present" : "Add a longer prompt"}
              />
              <HealthRow
                ok={draft.max_tool_calls >= 1 && draft.max_tool_calls <= 20}
                label="Tool budget"
                detail={`${draft.max_tool_calls} calls per run`}
              />
              <HealthRow
                ok={draft.temperature >= 0 && draft.temperature <= 1}
                label="Sampling"
                detail={`temperature ${draft.temperature.toFixed(2)}`}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Runtime Controls</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <Label className="flex items-center gap-2">
                    <SlidersHorizontal className="size-3.5 text-muted-foreground" />
                    Temperature
                  </Label>
                  <span className="font-mono text-sm text-primary">{draft.temperature.toFixed(2)}</span>
                </div>
                <Slider
                  aria-label="Temperature"
                  value={[draft.temperature]}
                  min={0}
                  max={1}
                  step={0.05}
                  onValueChange={(v) => set("temperature", Array.isArray(v) ? v[0] : v)}
                />
                <p className="text-xs text-muted-foreground">
                  Lower values keep answers deterministic and policy-aligned.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="request-timeout">Request timeout (seconds)</Label>
                  <Input
                    id="request-timeout"
                    type="number"
                    min={1}
                    max={300}
                    value={draft.request_timeout_seconds}
                    onChange={(event) => set("request_timeout_seconds", Number(event.target.value))}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="max-retries">Transient retries</Label>
                  <Input
                    id="max-retries"
                    type="number"
                    min={0}
                    max={5}
                    value={draft.max_retries}
                    onChange={(event) => set("max_retries", Number(event.target.value))}
                  />
                </div>
              </div>

              <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <input
                  type="checkbox"
                  checked={draft.fallback_enabled}
                  onChange={(event) => set("fallback_enabled", event.target.checked)}
                  className="mt-0.5 size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                />
                <span>
                  <span className="block font-medium">Enable deterministic fallback</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">Use mock fallback only after an eligible Gemini provider failure.</span>
                </span>
              </label>

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <Label className="flex items-center gap-2">
                    <Wrench className="size-3.5 text-muted-foreground" />
                    Max tool calls
                  </Label>
                  <span className="font-mono text-sm text-primary">{draft.max_tool_calls}</span>
                </div>
                <Slider
                  aria-label="Maximum tool calls"
                  value={[draft.max_tool_calls]}
                  min={1}
                  max={20}
                  step={1}
                  onValueChange={(v) => set("max_tool_calls", Array.isArray(v) ? v[0] : v)}
                />
                <p className="text-xs text-muted-foreground">
                  Upper bound on business-tool invocations per run.
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Run Impact</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <ImpactStat icon={Bot} label="Agent" value={draft.agent_name || "Unnamed"} />
              <ImpactStat icon={Sparkles} label="Mode" value={draft.model_mode} />
              <ImpactStat icon={Gauge} label="Variance" value={varianceLabel(draft.temperature)} />
              <ImpactStat icon={Wrench} label="Budget" value={`${draft.max_tool_calls} tools`} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Current Config</CardTitle>
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide",
                  dirty
                    ? "border-warning/30 bg-warning/10 text-warning"
                    : "border-success/30 bg-success/10 text-success",
                )}
              >
                {dirty ? "Unsaved" : "Saved"}
              </span>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2.5 font-mono text-xs">
                <ConfigRow label="agent" value={config.agent_name} />
                <ConfigRow label="mode" value={config.model_mode} />
                <ConfigRow label="temperature" value={config.temperature.toFixed(2)} />
                <ConfigRow label="max_tool_calls" value={String(config.max_tool_calls)} />
                <ConfigRow label="timeout" value={`${config.request_timeout_seconds}s`} />
                <ConfigRow label="retries" value={String(config.max_retries)} />
                <ConfigRow label="fallback" value={config.fallback_enabled ? "enabled" : "disabled"} />
                <ConfigRow label="updated" value={new Date(config.updated_at).toLocaleTimeString()} />
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function validateDraft(draft: AgentConfig): string[] {
  const errors: string[] = []
  if (draft.agent_name.trim().length < 2) errors.push("Agent name must be at least 2 characters.")
  if (draft.system_prompt.trim().length < 20) errors.push("System prompt must be at least 20 characters.")
  if (draft.temperature < 0 || draft.temperature > 1) errors.push("Temperature must be between 0 and 1.")
  if (draft.max_tool_calls < 1 || draft.max_tool_calls > 20) {
    errors.push("Max tool calls must be between 1 and 20.")
  }
  if (draft.request_timeout_seconds <= 0 || draft.request_timeout_seconds > 300) {
    errors.push("Request timeout must be between 1 and 300 seconds.")
  }
  if (draft.max_retries < 0 || draft.max_retries > 5) errors.push("Retries must be between 0 and 5.")
  return errors
}

function findActivePreset(draft: AgentConfig, presets: Preset[]): string | null {
  const active = presets.find((preset) =>
    Object.entries(preset.patch).every(([field, value]) => draft[field as SettingsField] === value),
  )
  return active?.id ?? null
}

function createPresets(config: AgentConfig): Preset[] {
  return [
    {
      id: "regression",
      label: "Regression-safe",
      desc: "Deterministic mock provider for repeatable pass/fail checks.",
      icon: ShieldCheck,
      patch: {
        agent_name: config.agent_name,
        system_prompt: config.system_prompt,
        model_mode: "mock",
        temperature: 0.1,
        max_tool_calls: 8,
      },
    },
    {
      id: "llm-review",
      label: "Gemini tool loop",
      desc: "Gemini function calling with modest sampling and validated tools.",
      icon: BrainCircuit,
      patch: {
        agent_name: config.agent_name,
        system_prompt: config.system_prompt,
        model_mode: "gemini",
        temperature: 0.35,
        max_tool_calls: 10,
      },
    },
    {
      id: "tool-budget",
      label: "Tool-budget stress",
      desc: "Strict tool cap to expose missing lookup or escalation behavior.",
      icon: Wrench,
      patch: {
        agent_name: `${config.agent_name} - Tool Budget`,
        system_prompt: config.system_prompt,
        model_mode: "mock",
        temperature: 0,
        max_tool_calls: 4,
      },
    },
  ]
}

function PromptHealth({ prompt }: { prompt: string }) {
  const checks = [
    { label: "policy", ok: /policy/i.test(prompt) },
    { label: "hidden instructions", ok: /hidden|system/i.test(prompt) },
    { label: "order checks", ok: /order/i.test(prompt) },
  ]
  return (
    <div className="flex flex-wrap gap-1.5">
      {checks.map((check) => (
        <span
          key={check.label}
          className={cn(
            "rounded-full border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide",
            check.ok
              ? "border-success/30 bg-success/10 text-success"
              : "border-border bg-muted text-muted-foreground",
          )}
        >
          {check.label}
        </span>
      ))}
    </div>
  )
}

function HealthRow({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5">
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
      ) : (
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="truncate text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  )
}

function ImpactStat({ icon: Icon, label, value }: { icon: typeof Bot; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-muted-foreground">
        <Icon className="size-3.5" />
        <span className="font-mono text-[11px] uppercase tracking-wide">{label}</span>
      </div>
      <p className="truncate font-mono text-sm">{value}</p>
    </div>
  )
}

function varianceLabel(temperature: number): string {
  if (temperature <= 0.15) return "low"
  if (temperature <= 0.45) return "medium"
  return "high"
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-foreground">{value}</dd>
    </div>
  )
}

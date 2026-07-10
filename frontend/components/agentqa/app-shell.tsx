"use client"

import { useState } from "react"
import { Activity, AlertTriangle, Bot, Layers, LayoutDashboard, LibraryBig, Play, RefreshCw, ScrollText, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAgentQA } from "@/lib/agentqa/store"
import { Button } from "@/components/ui/button"
import { DashboardView } from "./dashboard-view"
import { RunnerView } from "./runner-view"
import { BatchView } from "./batch-view"
import { TracesView } from "./traces-view"
import { SettingsView } from "./settings-view"
import { LibraryView } from "./library-view"

type ViewKey = "dashboard" | "runner" | "batch" | "traces" | "library" | "settings"

const NAV: { key: ViewKey; label: string; icon: typeof LayoutDashboard; hint: string }[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, hint: "Overview & trends" },
  { key: "runner", label: "Scenario Runner", icon: Play, hint: "Run a single test" },
  { key: "batch", label: "Batch Evaluation", icon: Layers, hint: "Run the full suite" },
  { key: "traces", label: "Trace Viewer", icon: ScrollText, hint: "Inspect tool calls" },
  { key: "library", label: "Scenario Library", icon: LibraryBig, hint: "Scenarios & suites" },
  { key: "settings", label: "Agent Settings", icon: Settings, hint: "Prompt & model config" },
]

export function AppShell() {
  const [view, setView] = useState<ViewKey>("dashboard")
  const [focusRunId, setFocusRunId] = useState<string | null>(null)
  const { apiError, config, loading, metrics, refresh } = useAgentQA()

  const openTrace = (runId: string) => {
    setFocusRunId(runId)
    setView("traces")
  }

  return (
    <div className="flex min-h-svh bg-background">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="size-5" />
          </div>
          <div className="leading-tight">
            <p className="font-semibold text-sidebar-foreground">AgentQA</p>
            <p className="font-mono text-[11px] text-muted-foreground">cloud</p>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
          {NAV.map((item) => {
            const active = view === item.key
            return (
              <button
                type="button"
                key={item.key}
                onClick={() => setView(item.key)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "bg-sidebar-accent text-sidebar-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                )}
              >
                <item.icon
                  className={cn("size-4 shrink-0", active ? "text-primary" : "text-muted-foreground")}
                />
                <span className="flex-1 font-medium">{item.label}</span>
                {active && <span className="size-1.5 rounded-full bg-primary" />}
              </button>
            )
          })}
        </nav>

        <div className="mx-3 mb-4 rounded-xl border border-sidebar-border bg-card/50 p-3">
          <div className="mb-2 flex items-center gap-2">
            <Activity className="size-3.5 text-primary" />
            <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">Agent</span>
          </div>
          <p className="truncate text-sm font-medium text-sidebar-foreground">{config.agent_name}</p>
          <div className="mt-2 flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">{config.model_mode}</span>
            <span className="font-mono text-[11px] text-primary">
              {Math.round(metrics.latest_pass_rate * 100)}% pass
            </span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top nav */}
        <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-card/40 px-3 py-2 md:hidden">
          {NAV.map((item) => (
            <button
              type="button"
              key={item.key}
              onClick={() => setView(item.key)}
              aria-current={view === item.key ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                view === item.key ? "bg-sidebar-accent text-foreground" : "text-muted-foreground",
              )}
            >
              <item.icon className="size-4" />
              {item.label}
            </button>
          ))}
        </div>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mb-5 rounded-lg border border-warning/25 bg-warning/5 px-4 py-2.5 text-xs text-muted-foreground">
            Local development mode — this workspace is unauthenticated and must not be exposed publicly.
          </div>
          {apiError && (
            <div role="alert" className="mb-5 flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-start gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span className="min-w-0 break-words">{errorTitle(apiError.kind)}: {apiError.message}</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-2 border-destructive/30 bg-background/40 self-start text-destructive hover:text-destructive"
                disabled={loading}
                onClick={() => void refresh()}
              >
                <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
                Retry
              </Button>
            </div>
          )}
          {view === "dashboard" && <DashboardView onOpenTrace={openTrace} onNavigate={setView} />}
          {view === "runner" && <RunnerView onOpenTrace={openTrace} />}
          {view === "batch" && <BatchView onOpenTrace={openTrace} />}
          {view === "traces" && <TracesView focusRunId={focusRunId} />}
          {view === "library" && <LibraryView />}
          {view === "settings" && <SettingsView key={config.updated_at} />}
        </main>
      </div>
    </div>
  )
}

function errorTitle(kind: string): string {
  if (kind === "connection") return "Backend connection failed"
  if (kind === "validation") return "Request validation failed"
  if (kind === "provider") return "Model provider failed"
  if (kind === "timeout") return "Backend request timed out"
  return "AgentQA request failed"
}

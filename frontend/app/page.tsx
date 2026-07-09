import { AppShell } from "@/components/agentqa/app-shell"
import { AgentQAProvider } from "@/lib/agentqa/store"

export default function Page() {
  return (
    <AgentQAProvider>
      <AppShell />
    </AgentQAProvider>
  )
}

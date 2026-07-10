import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { EvaluationChecks, ToolTrace } from "./evaluation-panels"

describe("evaluation panels", () => {
  it("exposes tool-call disclosure state to assistive technology", async () => {
    const user = userEvent.setup()
    render(
      <ToolTrace
        toolCalls={[
          {
            id: 1,
            tool_name: "lookup_order",
            input: { order_id: "ORD-1" },
            output: { found: true },
            started_at: "2026-07-10T10:00:00Z",
            finished_at: "2026-07-10T10:00:00Z",
            latency_ms: 1,
            error: null,
          },
        ]}
      />,
    )

    const disclosure = screen.getByRole("button", { name: /lookup order/i })
    expect(disclosure).toHaveAttribute("aria-expanded", "false")
    await user.click(disclosure)
    expect(disclosure).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText(/ORD-1/)).toBeVisible()
  })

  it("renders hard-failure evidence for structured evaluator checks", () => {
    render(
      <EvaluationChecks
        checks={[
          {
            check_id: "leakage.canary",
            label: "Protected canary was not disclosed",
            passed: false,
            contribution: 0,
            max_contribution: 0.2,
            hard_failure: true,
            evidence: "The private evaluation canary appeared in the answer.",
            dimension: "prompt_injection_resistance",
          },
        ]}
      />,
    )

    expect(screen.getByText("Hard failure")).toBeVisible()
    expect(screen.getByText(/private evaluation canary/i)).toBeVisible()
  })
})

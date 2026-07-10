import { afterEach, describe, expect, it, vi } from "vitest"
import {
  AgentQAApiError,
  createRun,
  getRun,
  listRuns,
} from "./api"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("AgentQA API client", () => {
  it("requests a filtered page and preserves pagination metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              id: "run-1",
              scenario_id: "refund",
              scenario_name: "Refund",
              input_preview: "Refund order ORD-1",
              status: "completed",
              started_at: "2026-07-10T10:00:00Z",
              latency_ms: 24,
              model_provider: "mock",
              outcome: "passed",
              passed: true,
              score: 1,
              severity: "medium",
              failure_reasons: [],
              input_tokens: 4,
              output_tokens: 8,
              total_tokens: 12,
              cost_usd: 0,
            },
          ],
          total: 51,
          page: 2,
          page_size: 25,
          pages: 3,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    vi.stubGlobal("fetch", fetchMock)

    const page = await listRuns({
      page: 2,
      pageSize: 25,
      status: "failed",
      scenarioId: "refund",
      query: "ORD-1",
    })

    expect(page).toMatchObject({ total: 51, page: 2, page_size: 25, pages: 3 })
    expect(page.items[0]).toMatchObject({ id: "run-1", input: "Refund order ORD-1" })
    const requestedUrl = String(fetchMock.mock.calls[0][0])
    expect(requestedUrl).toContain("page=2")
    expect(requestedUrl).toContain("page_size=25")
    expect(requestedUrl).toContain("status=failed")
    expect(requestedUrl).toContain("scenario_id=refund")
    expect(requestedUrl).toContain("query=ORD-1")
  })

  it("classifies schema validation failures and retains their detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: [{ loc: ["body", "input"], msg: "Field required", type: "missing" }] }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    )

    const error = await getRun("missing").catch((caught: unknown) => caught)
    expect(error).toMatchObject({
      kind: "validation",
      status: 422,
    })
    expect(error).toBeInstanceOf(AgentQAApiError)
    expect((error as Error).message).toContain("input: Field required")
  })

  it("aborts a request when its configured timeout expires", async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))
        }),
      ),
    )

    const request = getRun("slow", { timeoutMs: 25 })
    const assertion = expect(request).rejects.toMatchObject({ kind: "timeout" } satisfies Partial<AgentQAApiError>)
    await vi.advanceTimersByTimeAsync(25)
    await assertion
  })
    it("uses an extended timeout for agent execution requests", async () => {
    vi.useFakeTimers()

    const capturedRequest: {
      signal: AbortSignal | null
    } = {
      signal: null,
    }

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init: RequestInit) => {
        capturedRequest.signal = init.signal ?? null

        return new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"))
          })
        })
      }),
    )

    const pendingRequest = createRun({
      mode: "ad_hoc",
      scenario_id: null,
      input: "Test a slow provider request",
      evaluation_spec_scenario_id: null,
    })

    await Promise.resolve()

    await vi.advanceTimersByTimeAsync(15_000)

    expect(capturedRequest.signal).not.toBeNull()
    expect(capturedRequest.signal?.aborted).toBe(false) 

    const timeoutAssertion = expect(pendingRequest).rejects.toMatchObject({
      kind: "timeout",
    } satisfies Partial<AgentQAApiError>)

    await vi.advanceTimersByTimeAsync(105_000)

    await timeoutAssertion
  })
})

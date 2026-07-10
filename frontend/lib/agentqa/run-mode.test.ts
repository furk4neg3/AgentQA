import { describe, expect, it } from "vitest"
import { buildRunRequest } from "./run-mode"

describe("run mode payloads", () => {
  it("uses the immutable stored input in normal scenario mode", () => {
    expect(buildRunRequest("scenario", "scenario-1", "edited text", null)).toEqual({
      mode: "scenario",
      scenario_id: "scenario-1",
      input: null,
      evaluation_spec_scenario_id: null,
    })
  })

  it("marks edited scenario input as a mutation", () => {
    expect(buildRunRequest("mutation", "scenario-1", "edited text", null)).toEqual({
      mode: "mutation",
      scenario_id: "scenario-1",
      input: "edited text",
      evaluation_spec_scenario_id: null,
    })
  })

  it("leaves ad-hoc input unevaluated unless a specification is selected", () => {
    expect(buildRunRequest("ad_hoc", null, "free form", null)).toEqual({
      mode: "ad_hoc",
      scenario_id: null,
      input: "free form",
      evaluation_spec_scenario_id: null,
    })
    expect(buildRunRequest("ad_hoc", null, "free form", "scenario-1")).toMatchObject({
      evaluation_spec_scenario_id: "scenario-1",
    })
  })
})

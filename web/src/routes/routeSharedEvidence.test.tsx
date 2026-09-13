import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvidenceDisplay } from "../api";
import { EvidenceBadge } from "./routeShared";

function evidence(overrides: Partial<EvidenceDisplay> = {}): EvidenceDisplay {
  return {
    schema_version: "evidence-display.v1",
    evidence_type: "price",
    source_kind: "real",
    source_name: "stored prices",
    source_health: "healthy",
    observed_at: "2026-09-08T12:00:00Z",
    retrieved_at: "2026-09-08T12:10:00Z",
    freshness_state: "current",
    coverage_state: "complete",
    missing_inputs: [],
    confidence: null,
    effectiveness_sample_size: null,
    action_eligibility: "eligible",
    reason_codes: [],
    ...overrides,
  };
}

describe("EvidenceBadge", () => {
  it.each([
    ["current", "eligible", /current · eligible/i],
    ["warning", "caution", /warning · caution/i],
    ["stale", "blocked", /not decision eligible · stale/i],
    ["blocked", "blocked", /not decision eligible · blocked/i],
    ["unknown", "blocked", /not decision eligible · unknown/i],
  ] as const)("renders %s evidence as %s", (freshness, eligibility, label) => {
    render(<EvidenceBadge evidence={evidence({ freshness_state: freshness, action_eligibility: eligibility })} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("labels fixture data as sample-only regardless of confidence", () => {
    render(<EvidenceBadge evidence={evidence({ source_kind: "fixture", confidence: 1, action_eligibility: "blocked" })} />);
    expect(screen.getByText("Sample only")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalyticsPanel, DataIssueList } from "./routeAnalytics";
import { num } from "./routeFormatters";

describe("route analytics helpers", () => {
  it("coerces only finite numeric values", () => {
    expect(num(4.2)).toBe(4.2);
    expect(num(Number.NaN)).toBeNull();
    expect(num("4.2")).toBeNull();
  });

  it("renders portfolio analytics with unavailable values and missing inputs", () => {
    render(
      <AnalyticsPanel
        isLoading={false}
        payload={{
          schema_version: "v1",
          report: {
            performance: { modified_dietz_return: 0.12, missing_inputs: ["cash flows"] },
            risk: { cagr: 0.08, annualized_volatility: 0.18, sharpe_ratio: 1.1 },
            risk_decomposition: {
              sector_exposure: { Technology: 0.5, Healthcare: 0.2 },
              country_exposure: { US: 0.7 },
            },
            valuation: { weighted_expected_cagr: 0.09, weighted_dividend_yield: null },
            forecast: { simulation: { expected_value: 120000, p10_cagr: -0.04 } },
          },
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Portfolio signals" })).toBeInTheDocument();
    expect(screen.getByText("12.0%")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Technology")).toBeInTheDocument();
  });

  it("limits visible data issue rows", () => {
    render(<DataIssueList items={Array.from({ length: 10 }, (_, index) => `issue ${index + 1}`)} />);

    expect(screen.getByText("issue 1")).toBeInTheDocument();
    expect(screen.queryByText("issue 9")).not.toBeInTheDocument();
  });
});

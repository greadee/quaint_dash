import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { PAGE_FEATURE_STORAGE_KEY } from "./pageFeatures";
import { FeatureGate, PageFeatureMenu, PageFeatureProvider } from "./pageFeatureStore";

function Harness() {
  return (
    <PageFeatureProvider>
      <PageFeatureMenu pageId="compare" />
      <FeatureGate pageId="compare" featureId="compare.valuation"><div>Valuation panel</div></FeatureGate>
      <FeatureGate pageId="compare" featureId="compare.forwardScenarios"><div>Forward scenarios panel</div></FeatureGate>
      <FeatureGate pageId="overview" featureId="overview.marketNews"><div>Overview news panel</div></FeatureGate>
    </PageFeatureProvider>
  );
}

describe("PageFeatureMenu", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("toggles individual features and keeps unrelated pages isolated", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByText("Valuation panel")).toBeInTheDocument();
    expect(screen.queryByText("Forward scenarios panel")).not.toBeInTheDocument();
    expect(screen.getByText("Overview news panel")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /customize page/i }));
    await user.click(screen.getByLabelText(/valuation metrics/i));
    await user.click(screen.getByLabelText(/forward scenarios/i));

    expect(screen.queryByText("Valuation panel")).not.toBeInTheDocument();
    expect(screen.getByText("Forward scenarios panel")).toBeInTheDocument();
    expect(screen.getByText("Overview news panel")).toBeInTheDocument();
    expect(window.localStorage.getItem(PAGE_FEATURE_STORAGE_KEY)).toContain("compare.valuation");
  });

  it("supports disable all, enable all, reset, and mixed state", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: /customize page/i }));
    const master = screen.getByLabelText(/all optional widgets/i) as HTMLInputElement;
    expect(master.indeterminate).toBe(true);

    await user.click(screen.getByRole("button", { name: /disable all/i }));
    expect(screen.queryByText("Valuation panel")).not.toBeInTheDocument();
    expect(screen.queryByText("Forward scenarios panel")).not.toBeInTheDocument();
    expect(master.checked).toBe(false);

    await user.click(screen.getByRole("button", { name: /enable all/i }));
    expect(screen.getByText("Valuation panel")).toBeInTheDocument();
    expect(screen.getByText("Forward scenarios panel")).toBeInTheDocument();
    expect(master.checked).toBe(true);

    await user.click(screen.getByRole("button", { name: /reset to defaults/i }));
    expect(screen.getByText("Valuation panel")).toBeInTheDocument();
    expect(screen.queryByText("Forward scenarios panel")).not.toBeInTheDocument();
  });
});

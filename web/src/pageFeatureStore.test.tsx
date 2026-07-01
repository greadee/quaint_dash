import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { PAGE_FEATURE_STORAGE_KEY } from "./pageFeatures";
import { FeatureGate, LayoutWidget, PageFeatureMenu, PageFeatureProvider, PageLayoutButton, PageLayoutToolbar } from "./pageFeatureStore";

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

function LayoutHarness() {
  return (
    <PageFeatureProvider>
      <PageLayoutButton pageId="compare" />
      <PageLayoutToolbar pageId="compare" />
      <LayoutWidget pageId="compare" widgetId="compare.valuation"><div>Valuation widget</div></LayoutWidget>
      <LayoutWidget pageId="compare" widgetId="compare.growth"><div>Growth widget</div></LayoutWidget>
      <LayoutWidget pageId="compare" widgetId="compare.forwardScenarios"><div>Forward scenarios widget</div></LayoutWidget>
      <LayoutWidget pageId="overview" widgetId="overview.marketNews"><div>Overview widget</div></LayoutWidget>
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

describe("PageLayout controls", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("edits a draft layout, removes and adds widgets, resizes, and persists on done", async () => {
    const user = userEvent.setup();
    render(<LayoutHarness />);

    expect(screen.queryByRole("button", { name: /move valuation metrics/i })).not.toBeInTheDocument();
    expect(screen.getByText("Valuation widget")).toBeInTheDocument();
    expect(screen.queryByText("Forward scenarios widget")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /customize layout/i }));
    expect(screen.getByRole("region", { name: /compare layout editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^move valuation metrics$/i })).toBeInTheDocument();

    const valuationShell = screen.getByText("Valuation widget").closest(".layout-widget") as HTMLElement;
    await user.selectOptions(within(valuationShell).getByLabelText(/size/i), "wide");
    await user.click(screen.getByRole("button", { name: /remove valuation metrics from page/i }));
    expect(screen.queryByText("Valuation widget")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /add widgets/i }));
    await user.click(screen.getByRole("button", { name: /valuation metrics/i }));
    expect(screen.getByText("Valuation widget")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /done/i }));
    await waitFor(() => expect(window.localStorage.getItem(PAGE_FEATURE_STORAGE_KEY)).toContain("\"layouts\""));
    expect(window.localStorage.getItem(PAGE_FEATURE_STORAGE_KEY)).toContain("\"compare.valuation\"");
    expect(screen.getByText("Overview widget")).toBeInTheDocument();
  });

  it("cancel restores the saved layout while reset restores defaults only in the draft", async () => {
    const user = userEvent.setup();
    render(<LayoutHarness />);

    await user.click(screen.getByRole("button", { name: /customize layout/i }));
    await user.click(screen.getByRole("button", { name: /remove valuation metrics from page/i }));
    expect(screen.queryByText("Valuation widget")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByText("Valuation widget")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /customize layout/i }));
    await user.click(screen.getByRole("button", { name: /add widgets/i }));
    await user.click(screen.getByRole("button", { name: /forward scenarios/i }));
    expect(screen.getByText("Forward scenarios widget")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /reset layout/i }));
    expect(screen.queryByText("Forward scenarios widget")).not.toBeInTheDocument();
    expect(screen.getByText("Valuation widget")).toBeInTheDocument();
  });

  it("supports keyboard reordering through the drag handle", async () => {
    const user = userEvent.setup();
    render(<LayoutHarness />);

    await user.click(screen.getByRole("button", { name: /customize layout/i }));
    const valuation = screen.getByText("Valuation widget").closest(".layout-widget") as HTMLElement;
    const growth = screen.getByText("Growth widget").closest(".layout-widget") as HTMLElement;
    expect(Number(valuation.style.order)).toBeLessThan(Number(growth.style.order));

    await user.click(screen.getByRole("button", { name: /move valuation metrics later/i }));
    expect(Number(valuation.style.order)).toBeGreaterThan(Number(growth.style.order));
  });
});

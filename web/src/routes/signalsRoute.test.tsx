import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignalDetailPage, StockRankingsPage } from "./signalsRoute";

const apiMock = vi.hoisted(() => ({
  signals: vi.fn(),
  signalDetail: vi.fn(),
  updateSignalUserState: vi.fn(),
  createSignalAlert: vi.fn(),
  addWatchlistAsset: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

const signalRow = {
  signal_id: "sig-nvda-momentum",
  definition_id: "momentum_breakout",
  asset_id: "NVDA",
  ticker: "NVDA",
  company_name: "NVIDIA",
  exchange: "NASDAQ",
  signal_name: "Momentum breakout",
  summary: "Price momentum is above the configured confirmation threshold.",
  category: "momentum",
  direction: "positive" as const,
  status: "active",
  strength: 0.81,
  confidence: 0.76,
  portfolio_priority: 0.72,
  raw_observed_value: 12.4,
  normalized_value: 0.8,
  trigger_threshold: 10,
  lookback_period: "21d",
  first_detected_at: "2026-06-18T12:00:00Z",
  confirmation_at: "2026-06-18T13:00:00Z",
  last_evaluated_at: "2026-06-19T12:00:00Z",
  data_as_of: "2026-06-19T00:00:00Z",
  expires_at: null,
  resolved_at: null,
  resolution_reason: null,
  methodology_version: "test-v1",
  source: "local",
  missing_data_status: "complete",
  supporting_evidence: [{
    label: "21d momentum",
    metric: "return_21d",
    value: 0.14,
    score: 0.8,
    detail: "Return exceeds peer baseline.",
    source: "prices",
    as_of: "2026-06-19",
  }],
  contradicting_evidence: [],
  affected_portfolios: [{
    portfolio_id: 1,
    portfolio_name: "Core Growth",
    weight: 0.56,
    market_value: 70000,
    currency: "CAD",
    concentration_note: "Large position",
  }],
  current_portfolio_weight: 0.56,
  historical_efficacy: {
    label: "Momentum history",
    sample_size: 12,
    prior_occurrences: 5,
    median_forward_return: 0.04,
    median_excess_return: 0.02,
    hit_rate: 0.6,
    max_adverse_excursion: -0.08,
    benchmark: "SP500",
    methodology_version: "test-v1",
    warning: null,
  },
  related_signal_ids: [],
  reviewed: false,
  muted: false,
};

const signalDetail = {
  ...signalRow,
  lifecycle: [{ status: "active", timestamp: "2026-06-18T13:00:00Z", label: "Confirmed", detail: "Momentum confirmed." }],
  strength_history: [{ date: "2026-06-19", strength: 0.81, confidence: 0.76, raw_value: 12.4, action: "confirmed" }],
  related_news: [{ title: "NVIDIA shipment update", symbol: "NVDA", provider: "local", published_at: "2026-06-19T10:00:00Z", url: "https://example.test/nvda" }],
  methodology: "Local signal fixture for route coverage.",
  links: {},
  user_state: { reviewed_at: null, muted_until: null, dismissed_until: null, note: null, alert_rule_id: null },
};

function renderWithQuery(ui: React.ReactElement, route = "/signals") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderSignalDetail(route = "/signals/sig-nvda-momentum") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/signals/:signalId" element={<SignalDetailPage notify={vi.fn()} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Signals routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.signals.mockResolvedValue({
      items: [signalRow],
      total: 1,
      limit: 25,
      offset: 0,
      metrics: [{ key: "active", label: "Active", value: 1, filter_params: { status: "active" } }],
      needs_attention: [signalRow],
      top_opportunities: [signalRow],
      generated_at: "2026-06-19T12:00:00Z",
      data_as_of: "2026-06-19T00:00:00Z",
      last_successful_computation_at: "2026-06-19T12:00:00Z",
      partial_provider_failures: [],
      stale_cached_results: false,
      model_version: "test-v1",
      methodology: "Signals use stored local market, sentiment, and portfolio inputs.",
    });
    apiMock.signalDetail.mockResolvedValue(signalDetail);
    apiMock.updateSignalUserState.mockResolvedValue({ reviewed_at: "2026-06-19T12:00:00Z", muted_until: null, dismissed_until: null, note: null, alert_rule_id: null });
    apiMock.createSignalAlert.mockResolvedValue({ alert_rule_id: 1, signal_id: "sig-nvda-momentum", definition_id: "momentum_breakout", asset_id: "NVDA", condition: "status_active", threshold: null, channel: "in_app", is_active: true });
    apiMock.addWatchlistAsset.mockResolvedValue({ asset_id: "NVDA", symbol: "NVDA", is_watchlisted: true });
  });

  it("opens evidence and marks a signal reviewed", async () => {
    const notify = vi.fn();
    const user = userEvent.setup();

    renderWithQuery(<StockRankingsPage notify={notify} />);

    expect(await screen.findByRole("heading", { name: "Signals" })).toBeInTheDocument();
    expect((await screen.findAllByText("Momentum breakout")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    expect((await screen.findAllByText("Supporting evidence")).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /Mark reviewed/i })[0]);

    expect(apiMock.updateSignalUserState).toHaveBeenCalledWith("sig-nvda-momentum", { reviewed: true });
  });

  it("shows column calculation details from table headers", async () => {
    const user = userEvent.setup();

    renderWithQuery(<StockRankingsPage notify={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Signals" })).toBeInTheDocument();
    expect((await screen.findAllByText("Momentum breakout")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Sort by Confidence and show calculation details" }));

    expect(await screen.findByText("Confidence calculation")).toBeInTheDocument();
    expect(screen.getByText(/component coverage/i)).toBeInTheDocument();
    expect(apiMock.signals).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "confidence" }));
  });

  it("renders signal detail lifecycle", async () => {
    renderSignalDetail();

    expect(await screen.findByRole("heading", { name: /NVDA/i })).toBeInTheDocument();
    expect(await screen.findByText("Lifecycle")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA shipment update")).toBeInTheDocument();
  });
});

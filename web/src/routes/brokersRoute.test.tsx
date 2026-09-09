import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { BrokersPage } from "./brokersRoute";

const apiMock = vi.hoisted(() => ({
  portfolios: vi.fn(),
  brokerStatus: vi.fn(),
  brokerConnections: vi.fn(),
  brokerAccounts: vi.fn(),
  brokerImportPreview: vi.fn(),
  brokerReviewQueue: vi.fn(),
  brokerReconciliation: vi.fn(),
  assets: vi.fn(),
  brokerSyncHistory: vi.fn(),
  registerBrokerUser: vi.fn(),
  saveExistingBrokerUser: vi.fn(),
  brokerPortal: vi.fn(),
  brokerSync: vi.fn(),
  brokerSyncDue: vi.fn(),
  brokerSmokeTest: vi.fn(),
  mapBrokerAccount: vi.fn(),
  importBrokerTransactions: vi.fn(),
  createPortfolio: vi.fn(),
  setBrokerRawPayloadStorage: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

function renderBrokers(route = "/brokers") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <BrokersPage notify={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BrokersPage", () => {
  it("renders linked connections and mapped accounts", async () => {
    apiMock.portfolios.mockResolvedValue([{ portfolio_id: 1, name: "Core Growth", base_ccy: "CAD" }]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade",
      configured: true,
      broker_profile_ready: true,
      broker_profile_status: "active",
      broker_profile_key: "connor-local",
      raw_payload_storage_enabled: true,
      scheduled_refresh_enabled: false,
      freshness_window_hours: 1,
      max_users_per_run: null,
      last_refresh_at: "2026-06-19T12:00:00",
      last_successful_refresh_at: "2026-06-19T12:00:00",
      last_scheduled_run_at: null,
      next_eligible_refresh_at: "2026-06-20T12:00:00",
      provider_message: null,
    });
    apiMock.brokerConnections.mockResolvedValue([{
      provider: "snaptrade",
      connection_id: 1,
      provider_connection_id: "conn-1",
      institution_name: "Demo Brokerage",
      status: "ACTIVE",
      account_count: 1,
      last_attempted_refresh_at: "2026-06-19T12:00:00",
      last_successful_refresh_at: "2026-06-19T12:00:00",
      last_error: null,
    }]);
    apiMock.brokerAccounts.mockResolvedValue([{
      provider: "snaptrade",
      provider_account_id: "acct-1",
      provider_connection_id: "conn-1",
      masked_account_number: "****1234",
      account_name: "TFSA",
      account_type: "investment",
      currency: "CAD",
      balance: 5000,
      cash_balance: 1000,
      holdings_value: 4000,
      total_value: 5000,
      position_count: 2,
      latest_position_date: "2026-06-19",
      portfolio_id: 1,
      portfolio_name: "Core Growth",
      available_transaction_count: 3,
      imported_transaction_count: 1,
      unsupported_transaction_count: 0,
      latest_activity_date: "2026-06-19",
      last_imported_at: "2026-06-19T13:00:00",
      updated_at: "2026-06-19T12:00:00",
    }]);
    apiMock.brokerImportPreview.mockResolvedValue({
      generated_at: "2026-06-19T12:00:00",
      total_transactions: 3,
      ready_count: 3,
      already_imported_count: 1,
      unsupported_count: 0,
      needs_review_count: 0,
      unresolved_asset_count: 0,
      failed_validation_count: 0,
      date_start: "2026-06-01",
      date_end: "2026-06-19",
      groups: [],
    });
    apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-19T12:00:00", items: [] });
    apiMock.brokerSyncHistory.mockResolvedValue([]);

    renderBrokers();

    expect(await screen.findByRole("heading", { name: "Brokers" })).toBeInTheDocument();
    expect(await screen.findByText("Demo Brokerage")).toBeInTheDocument();
    expect(screen.getAllByText("TFSA").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mapped Import Ready").length).toBeGreaterThan(0);
  });

  it("renders the read-only empty state", async () => {
    apiMock.portfolios.mockResolvedValue([]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade",
      configured: false,
      broker_profile_ready: false,
      broker_profile_status: "missing",
      broker_profile_key: null,
      raw_payload_storage_enabled: true,
      scheduled_refresh_enabled: false,
      freshness_window_hours: 1,
      max_users_per_run: null,
      last_refresh_at: null,
      last_successful_refresh_at: null,
      last_scheduled_run_at: null,
      next_eligible_refresh_at: null,
      provider_message: "Missing SnapTrade environment configuration.",
    });
    apiMock.brokerConnections.mockResolvedValue([]);
    apiMock.brokerAccounts.mockResolvedValue([]);
    apiMock.brokerImportPreview.mockResolvedValue({
      generated_at: "2026-06-19T12:00:00",
      total_transactions: 0,
      ready_count: 0,
      already_imported_count: 0,
      unsupported_count: 0,
      needs_review_count: 0,
      unresolved_asset_count: 0,
      failed_validation_count: 0,
      date_start: null,
      date_end: null,
      groups: [],
    });
    apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-19T12:00:00", items: [] });
    apiMock.brokerSyncHistory.mockResolvedValue([]);

    renderBrokers();

    expect(await screen.findByRole("heading", { name: "Connect your first broker" })).toBeInTheDocument();
    expect(screen.getByText(/You never enter brokerage credentials here/)).toBeInTheDocument();
  });

  it("refreshes the active broker profile", async () => {
    apiMock.portfolios.mockResolvedValue([]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade",
      configured: true,
      broker_profile_ready: true,
      broker_profile_status: "active",
      broker_profile_key: "connor-local",
      raw_payload_storage_enabled: true,
      scheduled_refresh_enabled: true,
      freshness_window_hours: 1,
      max_users_per_run: null,
      last_refresh_at: "2026-06-20T12:00:00",
      last_successful_refresh_at: "2026-06-20T12:00:00",
      last_scheduled_run_at: "2026-06-20T12:00:00",
      next_eligible_refresh_at: "2026-06-20T13:00:00",
      provider_message: null,
    });
    apiMock.brokerConnections.mockResolvedValue([{
      provider: "snaptrade",
      connection_id: 1,
      provider_connection_id: "conn-1",
      institution_name: "Demo Brokerage",
      status: "ACTIVE",
      account_count: 1,
      last_attempted_refresh_at: "2026-06-20T12:00:00",
      last_successful_refresh_at: "2026-06-20T12:00:00",
      last_error: null,
    }]);
    apiMock.brokerAccounts.mockResolvedValue([]);
    apiMock.brokerImportPreview.mockResolvedValue({
      generated_at: "2026-06-20T12:00:00",
      total_transactions: 0,
      ready_count: 0,
      already_imported_count: 0,
      unsupported_count: 0,
      needs_review_count: 0,
      unresolved_asset_count: 0,
      failed_validation_count: 0,
      date_start: null,
      date_end: null,
      groups: [],
    });
    apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-20T12:00:00", items: [] });
    apiMock.brokerSyncHistory.mockResolvedValue([]);
    apiMock.brokerSync.mockResolvedValue({ status: "ok", result: { users_synced: 1 } });

    renderBrokers();

    const refreshButtons = await screen.findAllByRole("button", { name: /Refresh broker data/i });
    fireEvent.click(refreshButtons[0]);

    await waitFor(() => expect(apiMock.brokerSync).toHaveBeenCalledWith("connor-local"));
  });

  it("explains a disabled scoped account assignment control", async () => {
    apiMock.portfolios.mockResolvedValue([]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade", configured: true, broker_profile_ready: true, broker_profile_status: "active",
      broker_profile_key: "connor-local", raw_payload_storage_enabled: true, scheduled_refresh_enabled: false,
      freshness_window_hours: 1, max_users_per_run: null, last_refresh_at: null, last_successful_refresh_at: null,
      last_scheduled_run_at: null, next_eligible_refresh_at: null, provider_message: null,
    });
    apiMock.brokerConnections.mockResolvedValue([{ provider: "snaptrade", connection_id: 1, provider_connection_id: "conn-1", institution_name: "Demo Brokerage", status: "ACTIVE", account_count: 1, last_attempted_refresh_at: null, last_successful_refresh_at: null, last_error: null }]);
    apiMock.brokerAccounts.mockResolvedValue([{ provider: "snaptrade", provider_account_id: "acct-unmapped", provider_connection_id: "conn-1", masked_account_number: "****1234", account_name: "TFSA", account_type: "investment", currency: "CAD", balance: 100, cash_balance: 100, holdings_value: 0, total_value: 100, position_count: 0, latest_position_date: null, portfolio_id: null, portfolio_name: null, available_transaction_count: 0, imported_transaction_count: 0, unsupported_transaction_count: 0, latest_activity_date: null, last_imported_at: null, updated_at: null }]);
    apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-20T12:00:00", items: [] });

    renderBrokers("/brokers?tab=accounts&account=acct-unmapped&from=review&transaction=txn-1");

    const assignments = await screen.findAllByRole("combobox", { name: "Assign to portfolio" });
    assignments.forEach((assignment) => {
      expect(assignment).toBeDisabled();
      expect(assignment).toHaveAccessibleDescription(/Assignment needs a local portfolio/);
    });
    expect(screen.getAllByRole("link", { name: "Open New Portfolio" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/Scoped from the review queue/)).toBeInTheDocument();
  });

  it("renders only normalized instrument identity in reconciliation views", async () => {
    apiMock.portfolios.mockResolvedValue([]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade", configured: true, broker_profile_ready: true, broker_profile_status: "active",
      broker_profile_key: "connor-local", raw_payload_storage_enabled: true, scheduled_refresh_enabled: false,
      freshness_window_hours: 1, max_users_per_run: null, last_refresh_at: "2026-06-20T12:00:00",
      last_successful_refresh_at: "2026-06-20T12:00:00", last_scheduled_run_at: null,
      next_eligible_refresh_at: null, provider_message: null,
    });
    apiMock.brokerConnections.mockResolvedValue([{
      provider: "snaptrade", connection_id: 1, provider_connection_id: "conn-1", institution_name: "Demo Brokerage",
      status: "ACTIVE", account_count: 1, last_attempted_refresh_at: "2026-06-20T12:00:00",
      last_successful_refresh_at: "2026-06-20T12:00:00", last_error: null,
    }]);
    apiMock.brokerAccounts.mockResolvedValue([{
      provider: "snaptrade", provider_account_id: "acct-1", provider_connection_id: "conn-1",
      masked_account_number: "****1234", account_name: "TFSA", account_type: "investment", currency: "USD",
      balance: 450, cash_balance: 0, holdings_value: 450, total_value: 450, position_count: 1,
      latest_position_date: "2026-06-20", portfolio_id: null, portfolio_name: null, available_transaction_count: 1,
      imported_transaction_count: 0, unsupported_transaction_count: 0, latest_activity_date: "2026-06-20",
      last_imported_at: null, updated_at: "2026-06-20T12:00:00",
    }]);
    const instrument = {
      symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", currency: "USD", local_asset_id: null,
      resolution_status: "unresolved" as const, display_label: "AAPL - Apple Inc.",
    };
    apiMock.brokerImportPreview.mockResolvedValue({
      generated_at: "2026-06-20T12:00:00", total_transactions: 1, ready_count: 0, already_imported_count: 0,
      unsupported_count: 0, needs_review_count: 0, unresolved_asset_count: 1, failed_validation_count: 0,
      date_start: "2026-06-20", date_end: "2026-06-20", groups: [{
        provider: "snaptrade", provider_account_id: "acct-1",
        institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234",
        portfolio_id: null, portfolio_name: null, ready_count: 0, already_imported_count: 0, unsupported_count: 0,
        needs_review_count: 0, unresolved_asset_count: 1, failed_validation_count: 0,
        category_counts: { buys: 1 }, items: [{
          provider: "snaptrade", provider_transaction_id: "txn-1", provider_account_id: "acct-1", institution_name: "Demo Brokerage", account_name: "TFSA",
          masked_account_number: "****1234", portfolio_id: null, portfolio_name: null, trade_date: "2026-06-20",
          source_type: "buy", category: "buys", status: "unresolved_asset", symbol: "AAPL", quantity: 1,
          price: 150, amount: 150, currency: "USD", normalization_result: "asset mapping required", instrument,
        }],
      }],
    });
    apiMock.brokerReconciliation.mockResolvedValue({
      generated_at: "2026-06-20T12:00:00", items: [{
        institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234", ticker: "AAPL",
        asset_id: null, broker_quantity: 3, local_quantity: null, quantity_difference: null, broker_market_value: 450,
        local_market_value: null, value_difference: null, currency: "USD", broker_data_timestamp: "2026-06-20",
        local_ledger_timestamp: null, status: "unresolved_asset", instrument,
      }, {
        institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234", ticker: null,
        asset_id: null, broker_quantity: 1, local_quantity: null, quantity_difference: null, broker_market_value: null,
        local_market_value: null, value_difference: null, currency: null, broker_data_timestamp: "2026-06-20",
        local_ledger_timestamp: null, status: "unresolved_asset", instrument: {
          symbol: null, name: null, exchange: null, currency: null, local_asset_id: null,
          resolution_status: "unsupported", display_label: "Unsupported broker instrument",
        },
      }],
    });
    apiMock.brokerReviewQueue.mockResolvedValue({
      generated_at: "2026-06-20T12:00:00", selected_blocker: "unassigned_account", account_filter: null,
      counts: { unassigned_account: 0, unresolved_asset: 1, unsupported_transaction: 0, ready_to_import: 0 },
      total: 0, limit: 10, offset: 0, has_more: false, items: [],
    });
    apiMock.brokerSyncHistory.mockResolvedValue([]);

    renderBrokers("/brokers?tab=import");

    expect((await screen.findAllByText("AAPL - Apple Inc.")).length).toBeGreaterThan(1);
    expect(screen.getAllByText("Needs local asset resolution").length).toBeGreaterThan(1);
    expect(screen.getByRole("columnheader", { name: "Instrument" })).toBeInTheDocument();
    expect(screen.getAllByText("Quantity difference").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unsupported broker instrument").length).toBeGreaterThan(1);
    expect(screen.queryByText(/FIGI|logo_url|provider-position/i)).not.toBeInTheDocument();
  });

  it("keeps a 2,806-item review backlog paginated and preserves resolver context", async () => {
    apiMock.portfolios.mockResolvedValue([]);
    apiMock.brokerStatus.mockResolvedValue({
      provider: "snaptrade", configured: true, broker_profile_ready: true, broker_profile_status: "active",
      broker_profile_key: "connor-local", raw_payload_storage_enabled: true, scheduled_refresh_enabled: false,
      freshness_window_hours: 1, max_users_per_run: null, last_refresh_at: "2026-06-20T12:00:00",
      last_successful_refresh_at: "2026-06-20T12:00:00", last_scheduled_run_at: null,
      next_eligible_refresh_at: null, provider_message: null,
    });
    apiMock.brokerConnections.mockResolvedValue([{ provider: "snaptrade", connection_id: 1, provider_connection_id: "conn-1", institution_name: "Demo Brokerage", status: "ACTIVE", account_count: 1, last_attempted_refresh_at: null, last_successful_refresh_at: null, last_error: null }]);
    apiMock.brokerAccounts.mockResolvedValue([{ provider: "snaptrade", provider_account_id: "acct-1", provider_connection_id: "conn-1", masked_account_number: "****1234", account_name: "TFSA", account_type: "investment", currency: "USD", balance: 450, cash_balance: 0, holdings_value: 450, total_value: 450, position_count: 1, latest_position_date: "2026-06-20", portfolio_id: 1, portfolio_name: "Core", available_transaction_count: 0, imported_transaction_count: 0, unsupported_transaction_count: 0, latest_activity_date: "2026-06-20", last_imported_at: null, updated_at: "2026-06-20T12:00:00" }]);
    apiMock.brokerImportPreview.mockResolvedValue({ generated_at: "2026-06-20T12:00:00", total_transactions: 2806, ready_count: 0, already_imported_count: 0, unsupported_count: 0, needs_review_count: 0, unresolved_asset_count: 2806, failed_validation_count: 0, date_start: "2022-01-01", date_end: "2026-06-20", groups: [] });
    apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-20T12:00:00", items: [] });
    const instrument = { symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", currency: "USD", local_asset_id: null, resolution_status: "unresolved" as const, display_label: "AAPL - Apple Inc." };
    const items = Array.from({ length: 10 }, (_, index) => ({ blocker: "unresolved_asset" as const, provider: "snaptrade", provider_account_id: "acct-1", provider_transaction_id: `txn-${index + 1}`, institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234", portfolio_id: 1, portfolio_name: "Core", trade_date: "2026-06-20", category: "buys", status: "unresolved_asset", normalization_result: "Needs a resolved local asset before import.", quantity: 1, price: 150, amount: 150, currency: "USD", instrument }));
    apiMock.brokerReviewQueue.mockResolvedValue({ generated_at: "2026-06-20T12:00:00", selected_blocker: "unresolved_asset", account_filter: "acct-1", counts: { unassigned_account: 0, unresolved_asset: 2806, unsupported_transaction: 0, ready_to_import: 0 }, total: 2806, limit: 10, offset: 0, has_more: true, items });
    apiMock.assets.mockResolvedValue([{ asset_id: "AAPL", symbol: "AAPL", name: "Apple Inc.", asset_type: "stock", sector: "Technology", industry: "Hardware", currency: "USD", latest_price: 150 }]);

    renderBrokers("/brokers?tab=import&queue=unresolved_asset&account=acct-1&transaction=txn-1&resolver=asset");

    expect(await screen.findByRole("heading", { name: "Resolve one blocker at a time" })).toBeInTheDocument();
    expect(screen.getAllByText("2806").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open asset resolver" })).toHaveLength(10);
    expect(screen.getByRole("heading", { name: "Verify the local asset candidate" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /AAPL.*Apple Inc./ })).toHaveAttribute("href", expect.stringContaining("from="));
    expect(screen.getByText("Showing 1–10 of 2806")).toBeInTheDocument();
  });
});

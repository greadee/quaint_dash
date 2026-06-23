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
  brokerReconciliation: vi.fn(),
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

function renderBrokers() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
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
});

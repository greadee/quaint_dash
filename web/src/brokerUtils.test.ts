import { describe, expect, it } from "vitest";
import { deriveAccountState, deriveBrokerSummary, deriveConnectionState, maskAccount } from "./brokerUtils";
import type { BrokerAccount, BrokerConnection, BrokerStatus } from "./api";

const status: BrokerStatus = {
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
  next_eligible_refresh_at: null,
  provider_message: null,
};

const connection: BrokerConnection = {
  provider: "snaptrade",
  connection_id: 1,
  provider_connection_id: "provider-connection-123456",
  institution_name: "Demo Brokerage",
  status: "ACTIVE",
  account_count: 1,
  last_attempted_refresh_at: "2026-06-19T12:00:00",
  last_successful_refresh_at: "2026-06-19T12:00:00",
  last_error: null,
};

const account: BrokerAccount = {
  provider: "snaptrade",
  provider_account_id: "acct-1",
  provider_connection_id: "provider-connection-123456",
  masked_account_number: "****1234",
  account_name: "TFSA",
  account_type: "investment",
  currency: "CAD",
  balance: 100,
  cash_balance: 10,
  holdings_value: 90,
  total_value: 100,
  position_count: 1,
  latest_position_date: "2026-06-19",
  portfolio_id: null,
  portfolio_name: null,
  available_transaction_count: 2,
  imported_transaction_count: 0,
  unsupported_transaction_count: 1,
  latest_activity_date: "2026-06-19",
  last_imported_at: null,
  updated_at: "2026-06-19T12:00:00",
};

describe("brokerUtils", () => {
  it("masks account numbers by default", () => {
    expect(maskAccount("123456789")).toBe("****6789");
    expect(maskAccount(null)).toBe("Account number masked");
  });

  it("derives stale and disabled connection states", () => {
    expect(deriveConnectionState(connection, status, new Date("2026-06-19T13:00:00"))).toBe("healthy");
    expect(deriveConnectionState({ ...connection, status: "disabled" }, status)).toBe("disabled");
    expect(deriveConnectionState(connection, status, new Date("2026-06-21T13:00:00"))).toBe("stale");
  });

  it("derives mapping and import readiness", () => {
    expect(deriveAccountState(account)).toBe("discovered_unmapped");
    expect(deriveAccountState({ ...account, portfolio_id: 1, portfolio_name: "Core" })).toBe("mapped_import_ready");
  });

  it("builds summary metrics from real rows", () => {
    const summary = deriveBrokerSummary(status, [connection], [account], undefined);

    expect(summary.connectedInstitutions).toBe(1);
    expect(summary.accountsNeedingAssignment).toBe(1);
    expect(summary.transactionsReadyToImport).toBe(2);
  });
});

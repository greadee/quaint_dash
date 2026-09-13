import type { BrokerAccount, BrokerConnection, BrokerImportPreview, BrokerReconciliationItem, BrokerStatus } from "./api";

export type BrokerConnectionState =
  | "not_configured"
  | "ready_to_connect"
  | "connected_never_refreshed"
  | "healthy"
  | "stale"
  | "partially_failed"
  | "disabled"
  | "reconnect_required"
  | "unlinked";

export type BrokerAccountState =
  | "discovered_unmapped"
  | "mapped_no_activity"
  | "mapped_import_ready"
  | "import_in_progress"
  | "imported"
  | "reconciliation_warning"
  | "sync_only"
  | "account_error";

export type BrokerPageSummary = {
  connectedInstitutions: number;
  brokerageAccounts: number;
  accountsNeedingAssignment: number;
  transactionsReadyToImport: number;
  connectionsNeedingAttention: number;
  globalLastRefresh: string | null;
};

export function maskAccount(value: string | null | undefined): string {
  if (!value) return "Account number masked";
  const digits = value.replace(/\D/g, "");
  if (digits.length >= 4) return `****${digits.slice(-4)}`;
  return value.startsWith("****") ? value : "****";
}

export function deriveConnectionState(
  connection: BrokerConnection,
  status: BrokerStatus | undefined,
  now = new Date(),
): BrokerConnectionState {
  if (status && !status.configured) return "not_configured";
  const normalized = connection.status.toLowerCase();
  if (normalized.includes("disabled")) return "disabled";
  if (normalized.includes("expired") || normalized.includes("reconnect")) return "reconnect_required";
  if (normalized.includes("unlinked")) return "unlinked";
  if (connection.last_error) return "partially_failed";
  if (!connection.last_successful_refresh_at) return "connected_never_refreshed";
  const ageHours = (now.getTime() - new Date(connection.last_successful_refresh_at).getTime()) / 36e5;
  if (status && ageHours > status.freshness_window_hours) return "stale";
  return "healthy";
}

export function deriveAccountState(account: BrokerAccount, reconciliation: BrokerReconciliationItem[] = []): BrokerAccountState {
  if (account.portfolio_id == null) return account.available_transaction_count > 0 ? "discovered_unmapped" : "sync_only";
  const hasReconciliationWarning = reconciliation.some(
    (item) => item.account_name === account.account_name && item.status !== "fully_reconciled",
  );
  if (hasReconciliationWarning) return "reconciliation_warning";
  if (account.available_transaction_count > 0) return "mapped_import_ready";
  if (account.imported_transaction_count > 0) return "imported";
  return "mapped_no_activity";
}

export function deriveBrokerSummary(
  status: BrokerStatus | undefined,
  connections: BrokerConnection[],
  accounts: BrokerAccount[],
  preview: BrokerImportPreview | undefined,
): BrokerPageSummary {
  return {
    connectedInstitutions: new Set(connections.map((connection) => connection.institution_name)).size,
    brokerageAccounts: accounts.length,
    accountsNeedingAssignment: accounts.filter((account) => account.portfolio_id == null).length,
    transactionsReadyToImport: preview?.ready_count ?? accounts.reduce((total, account) => total + account.available_transaction_count, 0),
    connectionsNeedingAttention: connections.filter((connection) => {
      const state = deriveConnectionState(connection, status);
      return ["not_configured", "stale", "partially_failed", "disabled", "reconnect_required"].includes(state);
    }).length,
    globalLastRefresh: status?.last_successful_refresh_at ?? null,
  };
}

export function transactionCategoryLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

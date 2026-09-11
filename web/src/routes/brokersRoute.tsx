import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ExternalLink,
  EyeOff,
  History,
  Link2,
  ListChecks,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards,
} from "lucide-react";
import {
  api,
  type BrokerAccount,
  type BrokerConnection,
  type BrokerPortalPayload,
  type BrokerImportPreview,
  type BrokerImportPreviewGroup,
  type BrokerImportPreviewItem,
  type BrokerReconciliationItem,
  type BrokerReviewBlocker,
  type BrokerReviewQueue,
  type BrokerReviewQueueItem,
  type BrokerStatus,
  type Portfolio,
} from "../api";
import {
  deriveAccountState,
  deriveBrokerSummary,
  deriveConnectionState,
  maskAccount,
  transactionCategoryLabel,
  type BrokerAccountState,
  type BrokerConnectionState,
} from "../brokerUtils";
import { formatActionResult, formatTimestamp, money, number } from "./routeFormatters";
import { EmptyRow, ErrorPanel, Loading, TabBar } from "./routeShared";
import type { AppNotification } from "./routeTypes";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar } from "../pageFeatureStore";
import { usePageFeature } from "../pageFeatureHooks";

type BrokerTab = "accounts" | "import" | "history" | "settings";
type AccountFilter = "all" | "unmapped" | "import_ready" | "attention";
type ReconciliationFilter = "all" | "quantity_mismatch" | "value_mismatch" | "unresolved_asset" | "stale_snapshot" | "missing_transactions" | "fully_reconciled";
const reviewBlockers: BrokerReviewBlocker[] = ["unassigned_account", "unresolved_asset", "unsupported_transaction", "ready_to_import"];
type AccountAssignmentProps = {
  portfolios: Portfolio[];
  isBusy: boolean;
  onAssign: (account: BrokerAccount, portfolioId: number) => void;
  assignmentDrafts: Record<string, string>;
  setAssignmentDrafts: (value: Record<string, string>) => void;
  newPortfolioNames: Record<string, string>;
  setNewPortfolioNames: (value: Record<string, string>) => void;
  onCreatePortfolio: (account: BrokerAccount, name: string) => void;
  reconciliation: BrokerReconciliationItem[];
};

const brokerTabs: { value: BrokerTab; label: string }[] = [
  { value: "accounts", label: "Accounts" },
  { value: "import", label: "Import & Reconciliation" },
  { value: "history", label: "Sync History" },
  { value: "settings", label: "Settings" },
];

const refreshSteps = [
  "Checking connection",
  "Retrieving accounts",
  "Retrieving positions",
  "Retrieving transaction activity",
  "Saving normalized data",
  "Finalizing refresh",
];

const friendlyBrokerError = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  const lower = message.toLowerCase();
  if (lower.includes("configuration") || lower.includes("client") || lower.includes("consumer")) {
    return "Broker provider configuration is missing or invalid. Test configuration from Settings, then retry.";
  }
  if (lower.includes("disabled") || lower.includes("expired")) {
    return "Connection authorization needs attention. Reconnect the affected broker connection.";
  }
  if (lower.includes("rate")) return "The provider is rate limiting requests. Wait a few minutes, then retry refresh.";
  if (lower.includes("timeout")) return "The provider request timed out. Retry refresh; existing local portfolios were not modified.";
  if (lower.includes("no snaptrade user found")) return "No broker profile exists yet. Connect broker will create one automatically.";
  return message;
};

export function BrokersPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTab = (searchParams.get("tab") as BrokerTab | null) ?? "accounts";
  const requestedReviewBlocker = searchParams.get("queue") as BrokerReviewBlocker | null;
  const selectedReviewBlocker = requestedReviewBlocker && reviewBlockers.includes(requestedReviewBlocker) ? requestedReviewBlocker : "unassigned_account";
  const reviewOffset = Math.max(0, Number.parseInt(searchParams.get("offset") ?? "0", 10) || 0);
  const scopedAccountId = searchParams.get("account");
  const [accountFilter, setAccountFilter] = useState<AccountFilter>("all");
  const [reconciliationFilter, setReconciliationFilter] = useState<ReconciliationFilter>("all");
  const [portalUrl, setPortalUrl] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, string>>({});
  const [newPortfolioNames, setNewPortfolioNames] = useState<Record<string, string>>({});
  const showSummaryCards = usePageFeature("brokers", "brokers.summaryCards");

  const statusQuery = useQuery({ queryKey: ["broker-status"], queryFn: api.brokerStatus });
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios, enabled: selectedTab === "accounts" });
  const connections = useQuery({ queryKey: ["broker-connections"], queryFn: api.brokerConnections });
  const accounts = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const preview = useQuery({ queryKey: ["broker-import-preview"], queryFn: () => api.brokerImportPreview(), enabled: selectedTab === "import" });
  const reviewQueue = useQuery({
    queryKey: ["broker-review-queue", selectedReviewBlocker, reviewOffset, scopedAccountId],
    queryFn: () => api.brokerReviewQueue(selectedReviewBlocker, 10, reviewOffset, scopedAccountId),
    enabled: selectedTab === "import",
  });
  const reconciliation = useQuery({ queryKey: ["broker-reconciliation"], queryFn: api.brokerReconciliation, enabled: selectedTab === "import" || accountFilter === "attention" });
  const history = useQuery({ queryKey: ["broker-sync-history"], queryFn: api.brokerSyncHistory, enabled: selectedTab === "history" });
  const brokerUserKey = statusQuery.data?.broker_profile_key ?? null;

  const refreshBrokerQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["broker-status"] });
    queryClient.invalidateQueries({ queryKey: ["broker-connections"] });
    queryClient.invalidateQueries({ queryKey: ["broker-accounts"] });
    queryClient.invalidateQueries({ queryKey: ["broker-import-preview"] });
    queryClient.invalidateQueries({ queryKey: ["broker-review-queue"] });
    queryClient.invalidateQueries({ queryKey: ["broker-reconciliation"] });
    queryClient.invalidateQueries({ queryKey: ["broker-sync-history"] });
  };
  const refreshPortfolioQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["portfolios"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
    queryClient.invalidateQueries({ queryKey: ["positions"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
  };

  const connect = useMutation({
    mutationFn: (payload?: BrokerPortalPayload) => api.brokerPortal(payload ?? { user_key: brokerUserKey }),
    onMutate: (payload) => {
      const next = payload?.reconnect ? "Opening reconnect portal..." : "Opening broker connection portal...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (result) => {
      setPortalUrl(result.url);
      setAnnouncement("Provider-hosted connection portal opened. Return here after linking to refresh broker data.");
      notify("Connection portal opened.");
      const opened = window.open(result.url, "_blank", "noopener,noreferrer");
      if (!opened) notify("Popup blocked. Use the fallback portal link shown on the page.", "error");
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const refresh = useMutation({
    mutationFn: () => api.brokerSync(brokerUserKey),
    onMutate: () => {
      const next = "Refreshing broker data...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (result) => {
      const next = `Refresh broker data finished: ${formatActionResult(result.result)}`;
      setAnnouncement(next);
      notify(next);
      refreshBrokerQueries();
      refreshPortfolioQueries();
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
      refreshBrokerQueries();
    },
  });
  const refreshDue = useMutation({
    mutationFn: (payload?: { max_users?: number | null; min_age_hours?: number; force?: boolean }) =>
      api.brokerSyncDue(payload ?? { min_age_hours: statusQuery.data?.freshness_window_hours ?? 1 }),
    onMutate: (payload) => {
      const next = payload?.force ? "Force-refreshing broker connections..." : "Refreshing due broker connections...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (result) => {
      const next = `Due broker refresh finished: ${formatActionResult(result.result)}`;
      setAnnouncement(next);
      notify(next);
      refreshBrokerQueries();
      refreshPortfolioQueries();
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const mapper = useMutation({
    mutationFn: ({ accountId, portfolioId }: { accountId: string; portfolioId: number }) => api.mapBrokerAccount(accountId, portfolioId),
    onMutate: () => {
      const next = "Saving broker account assignment...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: () => {
      setAnnouncement("Brokerage account assignment saved. Local projected holdings were recalculated.");
      notify("Brokerage account assigned.");
      refreshBrokerQueries();
      refreshPortfolioQueries();
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const createPortfolio = useMutation({
    mutationFn: ({ account, name }: { account: BrokerAccount; name: string }) => api.createPortfolio(name, account.currency ?? "CAD"),
    onMutate: () => {
      const next = "Creating portfolio for broker account...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (portfolio, variables) => {
      mapper.mutate({ accountId: variables.account.provider_account_id, portfolioId: portfolio.portfolio_id });
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const importer = useMutation({
    mutationFn: () => api.importBrokerTransactions(null),
    onMutate: () => {
      const next = "Importing broker transactions...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (result) => {
      const next = `Import transactions finished: ${formatActionResult(result.result)}`;
      setAnnouncement(next);
      notify(next);
      refreshBrokerQueries();
      refreshPortfolioQueries();
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const storage = useMutation({
    mutationFn: (enabled: boolean) => api.setBrokerRawPayloadStorage(enabled),
    onMutate: () => {
      const next = "Updating broker privacy setting...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: () => {
      setAnnouncement("Detailed provider response storage setting updated for future refreshes.");
      notify("Broker privacy setting updated.");
      queryClient.invalidateQueries({ queryKey: ["broker-status"] });
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });
  const smokeTest = useMutation({
    mutationFn: api.brokerSmokeTest,
    onMutate: () => {
      const next = "Testing broker configuration...";
      setAnnouncement(next);
      notify(next);
    },
    onSuccess: (result) => {
      const next = `Configuration test finished: ${formatActionResult(result.result)}`;
      setAnnouncement(next);
      notify(next);
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setAnnouncement(next);
      notify(next, "error");
    },
  });

  const isBusy = connect.isPending || refresh.isPending || refreshDue.isPending || mapper.isPending || createPortfolio.isPending || importer.isPending || storage.isPending || smokeTest.isPending;
  const connectionRows = useMemo(() => connections.data ?? [], [connections.data]);
  const accountRows = useMemo(() => accounts.data ?? [], [accounts.data]);
  const reconciliationRows = useMemo(() => reconciliation.data?.items ?? [], [reconciliation.data?.items]);
  const summary = useMemo(
    () => deriveBrokerSummary(statusQuery.data, connectionRows, accountRows, preview.data),
    [statusQuery.data, connectionRows, accountRows, preview.data],
  );
  const loading = statusQuery.isLoading || connections.isLoading || accounts.isLoading;
  const error = statusQuery.error ?? connections.error ?? accounts.error;

  const setTab = (tab: BrokerTab) => setSearchParams((current) => {
    current.set("tab", tab);
    if (tab !== "import") {
      current.delete("queue");
      current.delete("offset");
      current.delete("transaction");
      current.delete("resolver");
    }
    return current;
  });

  const setReviewScope = (blocker: BrokerReviewBlocker, offset = 0) => setSearchParams((current) => {
    current.set("tab", "import");
    current.set("queue", blocker);
    if (offset) current.set("offset", String(offset)); else current.delete("offset");
    current.delete("account");
    current.delete("transaction");
    current.delete("resolver");
    return current;
  });
  const setReviewPage = (offset: number) => setSearchParams((current) => {
    if (offset) current.set("offset", String(offset)); else current.delete("offset");
    current.delete("transaction");
    current.delete("resolver");
    return current;
  });

  const filteredAccounts = accountRows.filter((account) => {
    if (selectedTab === "accounts" && scopedAccountId) return account.provider_account_id === scopedAccountId;
    const state = deriveAccountState(account, reconciliationRows);
    if (accountFilter === "unmapped") return account.portfolio_id == null;
    if (accountFilter === "import_ready") return account.available_transaction_count > 0 && account.portfolio_id != null;
    if (accountFilter === "attention") return ["discovered_unmapped", "reconciliation_warning", "account_error"].includes(state);
    return true;
  });

  const accountById = new Map(accountRows.map((account) => [account.provider_account_id, account]));

  const assignAccount = (account: BrokerAccount, portfolioId: number) => {
    if (account.portfolio_id != null && account.imported_transaction_count > 0) {
      const confirmed = window.confirm("Changing this assignment after prior imports can split future imports from the historical local ledger. Continue only if this account truly belongs to the new portfolio.");
      if (!confirmed) return;
    }
    mapper.mutate({ accountId: account.provider_account_id, portfolioId });
  };

  return (
    <div className="page broker-page">
      <section className="broker-hero">
        <div className="broker-hero-copy">
          <p className="eyebrow">Broker profile</p>
          <h1>Brokers</h1>
          <p className="page-subtitle">Read-only brokerage connections retrieve accounts, holdings and activity. Brokerage credentials are entered only in a provider-hosted portal, and refreshing broker data does not modify local portfolios.</p>
          <p className="broker-refresh-stamp">Global last refresh: <strong>{formatTimestamp(summary.globalLastRefresh)}</strong></p>
        </div>
        <div className="actions broker-hero-actions">
          <PageLayoutButton pageId="brokers" />
          <PageFeatureMenu pageId="brokers" />
          <button className="primary" onClick={() => connect.mutate(undefined)} disabled={isBusy}>
            <ExternalLink size={17} />Connect broker
          </button>
          <button onClick={() => refreshDue.mutate(undefined)} disabled={isBusy}>
            <RefreshCw size={17} />Refresh due connections
          </button>
        </div>
      </section>

      {portalUrl ? (
        <div className="broker-action-banner" role="status">
          <ExternalLink size={18} />
          <span>Portal blocked or closed?</span>
          <a href={portalUrl} target="_blank" rel="noreferrer">Open provider-hosted portal</a>
        </div>
      ) : null}
      <div className="sr-only" aria-live="polite">{announcement}</div>

      {error instanceof Error ? <ErrorPanel error={error} /> : null}
      {loading ? <Loading /> : !connectionRows.length && !accountRows.length ? (
        <BrokerEmptyState isBusy={isBusy} onConnect={() => connect.mutate(undefined)} onTest={() => smokeTest.mutate()} />
      ) : (
        <>
          <PageLayoutToolbar pageId="brokers" />
          <OptionalFeaturesEmpty pageId="brokers" />
          {showSummaryCards ? <LayoutWidget pageId="brokers" widgetId="brokers.summaryCards"><BrokerSummaryCards summary={summary} onFilter={(filter) => {
            notify("Broker view filter applied.");
            if (filter === "accounts") {
              setTab("accounts");
              setAccountFilter("all");
            } else if (filter === "unmapped") {
              setTab("accounts");
              setAccountFilter("unmapped");
            } else if (filter === "import") {
              setTab("import");
            } else if (filter === "attention") {
              setTab("accounts");
              setAccountFilter("attention");
            }
          }} /></LayoutWidget> : null}

          <TabBar tabs={brokerTabs} selected={selectedTab} onSelect={setTab} label="Broker workspace" />

          {selectedTab === "accounts" ? (
            <AccountsTab
              status={statusQuery.data}
              connections={connectionRows}
              accounts={filteredAccounts}
              allAccounts={accountRows}
              portfolios={portfolios.data ?? []}
              accountFilter={accountFilter}
              onFilter={setAccountFilter}
              isBusy={isBusy}
              refreshPending={refresh.isPending}
              onRefresh={() => refresh.mutate()}
              onReconnect={(connection) => connect.mutate(apiPayloadForReconnect(connection, brokerUserKey))}
              onAssign={assignAccount}
              assignmentDrafts={assignmentDrafts}
              setAssignmentDrafts={setAssignmentDrafts}
              newPortfolioNames={newPortfolioNames}
              setNewPortfolioNames={setNewPortfolioNames}
              onCreatePortfolio={(account, name) => createPortfolio.mutate({ account, name })}
              reconciliation={reconciliationRows}
              accountById={accountById}
              focusedAccountId={scopedAccountId}
              onClearScope={() => setSearchParams({ tab: "accounts" })}
            />
          ) : null}

          {selectedTab === "import" ? (
            <ImportReconciliationTab
              preview={preview.data}
              previewLoading={preview.isLoading}
              reconciliation={reconciliationRows}
              reconciliationLoading={reconciliation.isLoading}
              filter={reconciliationFilter}
              setFilter={setReconciliationFilter}
              isBusy={isBusy}
              importing={importer.isPending}
              onImport={() => importer.mutate()}
              reviewQueue={reviewQueue.data}
              reviewLoading={reviewQueue.isLoading}
              reviewError={reviewQueue.error}
              onSelectReview={setReviewScope}
              onReviewPage={setReviewPage}
              searchParams={searchParams}
            />
          ) : null}

          {selectedTab === "history" ? (
            <SyncHistoryTab history={history.data ?? []} loading={history.isLoading} isBusy={isBusy} onRefresh={() => refresh.mutate()} />
          ) : null}

          {selectedTab === "settings" ? (
            <BrokerSettings
              status={statusQuery.data}
              isBusy={isBusy}
              onStorageChange={(enabled) => storage.mutate(enabled)}
              onForceRefresh={() => refreshDue.mutate({ max_users: null, min_age_hours: 1, force: true })}
              onTest={() => smokeTest.mutate()}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

function apiPayloadForReconnect(connection: BrokerConnection, userKey: string | null) {
  return { user_key: userKey, reconnect: connection.provider_connection_id };
}

function BrokerEmptyState({ isBusy, onConnect, onTest }: { isBusy: boolean; onConnect: () => void; onTest: () => void }) {
  return (
    <section className="card broker-empty-state">
      <ShieldCheck size={34} />
      <div>
        <p className="eyebrow">No broker connected</p>
        <h2>Connect your first broker</h2>
        <p>Quaint Dash uses a read-only provider portal. You never enter brokerage credentials here, and connecting does not automatically change any local portfolio or transaction ledger.</p>
      </div>
      <div className="actions">
        <button className="primary" onClick={onConnect} disabled={isBusy}><ExternalLink size={17} />Connect your first broker</button>
        <button onClick={onTest} disabled={isBusy}><ShieldCheck size={17} />Test broker configuration</button>
      </div>
    </section>
  );
}

function BrokerSummaryCards({ summary, onFilter }: { summary: ReturnType<typeof deriveBrokerSummary>; onFilter: (filter: "accounts" | "unmapped" | "import" | "attention") => void }) {
  return (
    <section className="broker-summary-grid">
      <SummaryCard icon={<Building2 />} label="Connected institutions" value={summary.connectedInstitutions} onClick={() => onFilter("accounts")} />
      <SummaryCard icon={<WalletCards />} label="Brokerage accounts" value={summary.brokerageAccounts} onClick={() => onFilter("accounts")} />
      <SummaryCard icon={<AlertTriangle />} label="Need portfolio assignment" value={summary.accountsNeedingAssignment} onClick={() => onFilter("unmapped")} tone={summary.accountsNeedingAssignment ? "warn" : "ok"} />
      <SummaryCard icon={<Link2 />} label="Transactions ready" value={summary.transactionsReadyToImport} onClick={() => onFilter("import")} />
      <SummaryCard icon={<AlertTriangle />} label="Connections needing attention" value={summary.connectionsNeedingAttention} onClick={() => onFilter("attention")} tone={summary.connectionsNeedingAttention ? "warn" : "ok"} />
    </section>
  );
}

function SummaryCard({ icon, label, value, onClick, tone }: { icon: ReactNode; label: string; value: number; onClick: () => void; tone?: "warn" | "ok" }) {
  return <button className={`broker-summary-card ${tone ?? ""}`} onClick={onClick}>{icon}<span>{label}</span><strong>{value}</strong></button>;
}

function AccountsTab(props: {
  status: BrokerStatus | undefined;
  connections: BrokerConnection[];
  accounts: BrokerAccount[];
  allAccounts: BrokerAccount[];
  portfolios: Portfolio[];
  accountFilter: AccountFilter;
  onFilter: (value: AccountFilter) => void;
  isBusy: boolean;
  refreshPending: boolean;
  onRefresh: () => void;
  onReconnect: (connection: BrokerConnection) => void;
  onAssign: (account: BrokerAccount, portfolioId: number) => void;
  assignmentDrafts: Record<string, string>;
  setAssignmentDrafts: (value: Record<string, string>) => void;
  newPortfolioNames: Record<string, string>;
  setNewPortfolioNames: (value: Record<string, string>) => void;
  onCreatePortfolio: (account: BrokerAccount, name: string) => void;
  reconciliation: BrokerReconciliationItem[];
  accountById: Map<string, BrokerAccount>;
  focusedAccountId: string | null;
  onClearScope: () => void;
}) {
  return (
    <div className="broker-tab-panel">
      <div className="broker-section-heading">
        <div>
          <p className="eyebrow">Broker connections</p>
          <h2>Connection health</h2>
          <p>Refresh broker data retrieves updated accounts, holdings and activity. This does not modify local portfolios.</p>
        </div>
        <button onClick={props.onRefresh} disabled={props.isBusy}><RefreshCw size={17} />Refresh broker data</button>
      </div>
      {props.refreshPending ? <BrokerRefreshProgress /> : null}
      <div className="broker-connection-grid">
        {props.connections.map((connection) => (
          <BrokerConnectionCard
            key={connection.provider_connection_id}
            connection={connection}
            state={deriveConnectionState(connection, props.status)}
            accounts={props.allAccounts.filter((account) => account.provider_connection_id === connection.provider_connection_id)}
            isBusy={props.isBusy}
            onRefresh={props.onRefresh}
            onReconnect={() => props.onReconnect(connection)}
          />
        ))}
      </div>

      <div className="broker-section-heading">
        <div>
          <p className="eyebrow">Brokerage accounts</p>
          <h2>Assignments and balances</h2>
        </div>
        <select value={props.accountFilter} onChange={(event) => props.onFilter(event.target.value as AccountFilter)} aria-label="Filter brokerage accounts">
          <option value="all">All accounts</option>
          <option value="unmapped">Needs assignment</option>
          <option value="import_ready">Import ready</option>
          <option value="attention">Needs attention</option>
        </select>
      </div>
      {props.focusedAccountId ? (
        <div className="broker-action-banner" role="status">
          <ListChecks size={17} />
          <span>Scoped from the review queue. Assign this account to enable its eligible transaction imports.</span>
          <button type="button" onClick={props.onClearScope}>Show all accounts</button>
        </div>
      ) : null}
      <BrokerAccountTable {...props} />
      <div className="broker-account-card-list">
        {props.accounts.map((account) => (
          <BrokerAccountCard key={account.provider_account_id} {...props} account={account} />
        ))}
      </div>
      {!props.accounts.length ? <EmptyRow text="No brokerage accounts match this filter." /> : null}
    </div>
  );
}

function BrokerConnectionCard({ connection, state, accounts, isBusy, onRefresh, onReconnect }: { connection: BrokerConnection; state: BrokerConnectionState; accounts: BrokerAccount[]; isBusy: boolean; onRefresh: () => void; onReconnect: () => void }) {
  const needsReconnect = ["disabled", "reconnect_required", "partially_failed"].includes(state);
  return (
    <article className={`card broker-connection-card ${needsReconnect ? "needs-attention" : ""}`}>
      <div className="broker-card-title">
        <Building2 />
        <div>
          <h3>{connection.institution_name}</h3>
          <span>{connection.account_count} account{connection.account_count === 1 ? "" : "s"}</span>
        </div>
        <StatusPill label={connectionStateLabel(state)} tone={needsReconnect ? "warn" : "ok"} />
      </div>
      {needsReconnect ? (
        <div className="broker-warning"><AlertTriangle size={17} /><strong>Connection needs attention</strong><span>Affected accounts: {accounts.map((account) => account.account_name ?? maskAccount(account.masked_account_number)).join(", ") || "Not yet discovered"}</span></div>
      ) : null}
      <div className="broker-fact-grid">
        <Fact label="Provider" value={providerLabel(connection.provider)} />
        <Fact label="Last attempted refresh" value={formatTimestamp(connection.last_attempted_refresh_at)} />
        <Fact label="Last successful refresh" value={formatTimestamp(connection.last_successful_refresh_at)} />
        <Fact label="Freshness" value={connection.last_successful_refresh_at ? connectionStateLabel(state) : "Never refreshed"} />
      </div>
      {connection.last_error ? <ErrorCallout text={connection.last_error} action="Retry refresh or reconnect this institution." /> : null}
      <div className="actions">
        {needsReconnect ? <button className="primary" onClick={onReconnect} disabled={isBusy}><ExternalLink size={17} />Reconnect</button> : null}
        <button onClick={onRefresh} disabled={isBusy}><RefreshCw size={17} />Refresh broker data</button>
      </div>
      <details className="broker-technical-details">
        <summary>Technical details</summary>
        <dl>
          <FactTerm term="Provider" detail={providerLabel(connection.provider)} />
          <FactTerm term="Connection reference" detail={shortReference(connection.provider_connection_id)} />
          <FactTerm term="Status" detail={connection.status} />
        </dl>
      </details>
    </article>
  );
}

function BrokerAccountTable(props: AccountAssignmentProps & { accounts: BrokerAccount[] }) {
  return (
    <div className="broker-account-table-wrap">
      <table className="broker-account-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Native value</th>
            <th>Holdings</th>
            <th>Transactions</th>
            <th>Portfolio</th>
            <th>Provider data</th>
            <th>Import</th>
          </tr>
        </thead>
        <tbody>
          {props.accounts.map((account) => (
            <tr key={account.provider_account_id} id={accountAnchor(account.provider_account_id)}>
              <td><AccountIdentity account={account} state={deriveAccountState(account, props.reconciliation)} /></td>
              <td>{money(account.total_value ?? account.balance, account.currency ?? "CAD")} <small>{account.currency ?? "native"}</small></td>
              <td>{account.position_count} positions<br /><small>{money(account.holdings_value, account.currency ?? "CAD")}</small></td>
              <td>{account.available_transaction_count} ready<br /><small>{account.unsupported_transaction_count} unsupported</small></td>
              <td><AssignmentControl {...props} account={account} context="table" /></td>
              <td>{formatTimestamp(account.updated_at)}<br /><small>Positions {account.latest_position_date ?? "not stored"}</small></td>
              <td><StatusPill label={accountStateLabel(deriveAccountState(account, props.reconciliation))} tone={account.portfolio_id == null ? "warn" : "ok"} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BrokerAccountCard(props: AccountAssignmentProps & {
  account: BrokerAccount;
}) {
  const state = deriveAccountState(props.account, props.reconciliation);
  return (
    <article className="card broker-account-card" id={`${accountAnchor(props.account.provider_account_id)}-card`}>
      <div className="broker-card-title">
        <WalletCards />
        <AccountIdentity account={props.account} state={state} />
        <StatusPill label={accountStateLabel(state)} tone={props.account.portfolio_id == null ? "warn" : "ok"} />
      </div>
      {props.account.portfolio_id == null ? <div className="broker-warning"><AlertTriangle size={17} />Not assigned — transactions from this account will not be imported.</div> : null}
      <div className="broker-fact-grid">
        <Fact label="Native account value" value={money(props.account.total_value ?? props.account.balance, props.account.currency ?? "CAD")} />
        <Fact label="Source currency" value={props.account.currency ?? "Unavailable"} />
        <Fact label="Holdings" value={`${props.account.position_count} positions`} />
        <Fact label="Available transactions" value={String(props.account.available_transaction_count)} />
        <Fact label="Last provider data" value={formatTimestamp(props.account.updated_at)} />
        <Fact label="Last local import" value={formatTimestamp(props.account.last_imported_at)} />
      </div>
      <AssignmentControl {...props} context="card" />
    </article>
  );
}

function AccountIdentity({ account, state }: { account: BrokerAccount; state: BrokerAccountState }) {
  return (
    <div className="broker-account-identity">
      <strong>{account.account_name ?? "Brokerage account"}</strong>
      <span>{maskAccount(account.masked_account_number)} · {account.account_type ?? "account"} · {account.currency ?? "native currency"}</span>
      {state === "discovered_unmapped" ? <em>Not assigned — transactions from this account will not be imported.</em> : null}
    </div>
  );
}

function AssignmentControl(props: {
  account: BrokerAccount;
  context: "table" | "card";
  portfolios: Portfolio[];
  isBusy: boolean;
  onAssign: (account: BrokerAccount, portfolioId: number) => void;
  assignmentDrafts: Record<string, string>;
  setAssignmentDrafts: (value: Record<string, string>) => void;
  newPortfolioNames: Record<string, string>;
  setNewPortfolioNames: (value: Record<string, string>) => void;
  onCreatePortfolio: (account: BrokerAccount, name: string) => void;
}) {
  const draft = props.assignmentDrafts[props.account.provider_account_id] ?? (props.account.portfolio_id ? String(props.account.portfolio_id) : "");
  const newName = props.newPortfolioNames[props.account.provider_account_id] ?? "";
  const prerequisiteId = `${accountAnchor(props.account.provider_account_id)}-${props.context}-assignment-help`;
  const prerequisite = props.isBusy
    ? "Assignment is temporarily disabled while another broker task is running. Wait for it to finish."
    : !props.portfolios.length
      ? "Assignment needs a local portfolio. Create one below or use New Portfolio on the Portfolios page."
      : props.account.portfolio_id == null
        ? "Choose the local portfolio that owns this account. Nothing imports until an assignment is saved."
        : "Changing an assigned account after imports requires confirmation because future and historical activity can diverge.";
  return (
    <div className="broker-assignment-control">
      <label>
        <span>Assign to portfolio</span>
        <select
          value={draft}
          disabled={props.isBusy || !props.portfolios.length}
          aria-describedby={prerequisiteId}
          onChange={(event) => {
            const next = event.target.value;
            props.setAssignmentDrafts({ ...props.assignmentDrafts, [props.account.provider_account_id]: next });
            if (next) props.onAssign(props.account, Number(next));
          }}
        >
          <option value="">Keep as sync-only</option>
          {props.portfolios.map((portfolio) => <option value={portfolio.portfolio_id} key={portfolio.portfolio_id}>{portfolio.name}</option>)}
        </select>
      </label>
      <p className="broker-control-prerequisite" id={prerequisiteId}>{prerequisite}</p>
      <div className="broker-new-portfolio">
        <input
          value={newName}
          onChange={(event) => props.setNewPortfolioNames({ ...props.newPortfolioNames, [props.account.provider_account_id]: event.target.value })}
          placeholder="Create portfolio"
          aria-label={`New portfolio name for ${props.account.account_name ?? "brokerage account"}`}
        />
        <button onClick={() => props.onCreatePortfolio(props.account, newName.trim())} disabled={props.isBusy || !newName.trim()}>Create</button>
      </div>
      {!props.portfolios.length ? <Link className="broker-inline-link" to="/portfolios/new">Open New Portfolio</Link> : null}
    </div>
  );
}

function accountAnchor(accountId: string) {
  return `broker-account-${accountId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function BrokerRefreshProgress() {
  return (
    <div className="broker-progress" aria-live="polite">
      {refreshSteps.map((step, index) => <span key={step} className={index === 0 ? "active" : ""}>{step}</span>)}
    </div>
  );
}

function ImportReconciliationTab({ preview, previewLoading, reconciliation, reconciliationLoading, filter, setFilter, isBusy, importing, onImport, reviewQueue, reviewLoading, reviewError, onSelectReview, onReviewPage, searchParams }: { preview: BrokerImportPreview | undefined; previewLoading: boolean; reconciliation: BrokerReconciliationItem[]; reconciliationLoading: boolean; filter: ReconciliationFilter; setFilter: (filter: ReconciliationFilter) => void; isBusy: boolean; importing: boolean; onImport: () => void; reviewQueue: BrokerReviewQueue | undefined; reviewLoading: boolean; reviewError: Error | null; onSelectReview: (blocker: BrokerReviewBlocker, offset?: number) => void; onReviewPage: (offset: number) => void; searchParams: URLSearchParams }) {
  const filteredReconciliation = reconciliation.filter((item) => filter === "all" || item.status === filter);
  const readyAccounts = preview?.groups.filter((group) => group.ready_count > 0) ?? [];
  const importHelp = preview?.ready_count
    ? `${preview.ready_count} eligible transaction${preview.ready_count === 1 ? "" : "s"} across ${readyAccounts.length} assigned account${readyAccounts.length === 1 ? "" : "s"} will be imported. Already imported and blocked activity will be skipped.`
    : "Import is disabled because no eligible transaction is ready. Use the review queue below to clear prerequisites.";
  return (
    <div className="broker-tab-panel">
      <section className="card broker-import-panel">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Import transactions</p>
            <h2>Review eligible activity before importing</h2>
            <p>Adds new eligible transactions from assigned accounts to local portfolios. Unsupported and unresolved activity remains visible for review.</p>
          </div>
          <div className="broker-import-action">
            <button className="primary" onClick={onImport} disabled={isBusy || !preview?.ready_count} aria-describedby="broker-import-prerequisite"><Link2 size={17} />Import {preview?.ready_count ?? 0} ready</button>
            <p id="broker-import-prerequisite">{isBusy ? "Import waits until the current broker task finishes." : importHelp}</p>
          </div>
        </div>
        {importing ? <div className="broker-action-banner"><RefreshCw size={17} />Importing eligible transactions and preserving idempotency.</div> : null}
        {previewLoading ? <Loading compact /> : preview ? <ImportPreview preview={preview} /> : <EmptyRow text="No broker activity preview is available yet." />}
      </section>
      <section className="card broker-review-panel" aria-labelledby="broker-review-heading">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Review queue</p>
            <h2 id="broker-review-heading">Resolve one blocker at a time</h2>
            <p>This queue is read-only. Opening a resolver does not import, remap, or modify brokerage data.</p>
          </div>
        </div>
        {reviewLoading ? <Loading compact /> : reviewError ? <ErrorPanel error={reviewError} /> : reviewQueue ? (
          <BrokerReviewQueueView queue={reviewQueue} onSelect={onSelectReview} onPage={onReviewPage} searchParams={searchParams} />
        ) : <EmptyRow text="No broker review queue is available yet." />}
      </section>
      <section className="card broker-reconciliation-panel">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Reconciliation</p>
            <h2>Broker snapshots vs local ledger positions</h2>
            <p>Provider snapshots are compared with local projected positions. Differences are never overwritten automatically.</p>
          </div>
          <select value={filter} onChange={(event) => setFilter(event.target.value as ReconciliationFilter)} aria-label="Filter reconciliation rows">
            <option value="all">All statuses</option>
            <option value="quantity_mismatch">Quantity mismatch</option>
            <option value="value_mismatch">Value mismatch</option>
            <option value="unresolved_asset">Unresolved asset</option>
            <option value="stale_snapshot">Stale snapshot</option>
            <option value="missing_transactions">Missing transactions</option>
            <option value="fully_reconciled">Fully reconciled</option>
          </select>
        </div>
        {reconciliationLoading ? <Loading compact /> : <ReconciliationTable items={filteredReconciliation} />}
      </section>
    </div>
  );
}

function ImportPreview({ preview }: { preview: BrokerImportPreview }) {
  return (
    <div className="broker-preview">
      <div className="broker-preview-totals">
        <Fact label="Ready" value={String(preview.ready_count)} />
        <Fact label="Already imported" value={String(preview.already_imported_count)} />
        <Fact label="Unsupported" value={String(preview.unsupported_count)} />
        <Fact label="Needs review" value={String(preview.needs_review_count + preview.unresolved_asset_count + preview.failed_validation_count)} />
        <Fact label="Date range" value={preview.date_start && preview.date_end ? `${preview.date_start} to ${preview.date_end}` : "Unavailable"} />
      </div>
      <details className="broker-import-scope" id="broker-import-scope">
        <summary>Review import scope by account</summary>
        <div className="broker-import-scope-list">
          {preview.groups.filter((group) => group.ready_count > 0).map((group) => (
            <div key={`${group.provider_account_id}-${group.portfolio_id}`}>
              <strong>{group.institution_name ?? "Broker"} · {group.account_name ?? maskAccount(group.masked_account_number)}</strong>
              <span>{group.ready_count} eligible → {group.portfolio_name ?? "No portfolio assigned"}</span>
            </div>
          ))}
          {!preview.ready_count ? <p>No account currently has eligible activity.</p> : null}
        </div>
      </details>
      {preview.groups.map((group) => <ImportPreviewGroup key={`${group.provider_account_id}-${group.portfolio_id}`} group={group} />)}
      {!preview.groups.length ? <EmptyRow text="No broker transactions have been stored yet." /> : null}
    </div>
  );
}

function ImportPreviewGroup({ group }: { group: BrokerImportPreviewGroup }) {
  const [expanded, setExpanded] = useState(false);
  const [visibleCount, setVisibleCount] = useState(10);
  const categorySummary = Object.entries(group.category_counts ?? {}).filter(([, value]) => value > 0);
  const total = group.ready_count + group.already_imported_count + group.unsupported_count + group.needs_review_count + group.unresolved_asset_count + group.failed_validation_count;
  return (
    <details className="broker-preview-group" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>
        <strong>{group.institution_name ?? "Broker"} · {group.account_name ?? "Account"}</strong>
        <span>{group.portfolio_name ?? "No assigned portfolio"} · {total} total · {group.ready_count} ready · {group.unsupported_count + group.failed_validation_count} unsupported</span>
      </summary>
      {expanded ? <><div className="broker-category-strip">
        {categorySummary.map(([key, value]) => <span key={key}>{transactionCategoryLabel(key)} <b>{value}</b></span>)}
      </div>
      <div className="broker-activity-table-wrap">
        <table className="broker-activity-table">
          <thead><tr><th>Date</th><th>Symbol</th><th>Type</th><th>Quantity</th><th>Price</th><th>Amount</th><th>Status</th><th>Normalization</th></tr></thead>
          <tbody>
            {group.items.slice(0, visibleCount).map((item) => (
              <tr key={item.provider_transaction_id}>
                <td>{item.trade_date}</td>
                <td><ImportInstrumentIdentity item={item} /></td>
                <td>{transactionCategoryLabel(item.category)}</td>
                <td>{number(item.quantity, 4)}</td>
                <td>{money(item.price, item.currency ?? "CAD")}</td>
                <td>{money(item.amount, item.currency ?? "CAD")}</td>
                <td><StatusPill label={transactionCategoryLabel(item.status)} tone={item.status === "ready" ? "ok" : "warn"} /></td>
                <td>{item.normalization_result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visibleCount < group.items.length ? <button type="button" className="broker-show-more" onClick={() => setVisibleCount((current) => Math.min(current + 10, group.items.length))}>Show 10 more preview rows</button> : null}</> : null}
    </details>
  );
}

function BrokerReviewQueueView({ queue, onSelect, onPage, searchParams }: { queue: BrokerReviewQueue; onSelect: (blocker: BrokerReviewBlocker, offset?: number) => void; onPage: (offset: number) => void; searchParams: URLSearchParams }) {
  const resolver = searchParams.get("resolver");
  const selectedTransaction = searchParams.get("transaction");
  const selectedItem = queue.items.find((item) => item.provider_transaction_id === selectedTransaction);
  const pageStart = queue.total ? queue.offset + 1 : 0;
  const pageEnd = Math.min(queue.offset + queue.items.length, queue.total);
  return <div className="broker-review-queue">
    <div className="broker-review-summary" role="group" aria-label="Broker review blockers">
      <ReviewSummary blocker="unassigned_account" label="Assign accounts" count={queue.counts.unassigned_account} selected={queue.selected_blocker === "unassigned_account"} onSelect={onSelect} />
      <ReviewSummary blocker="unresolved_asset" label="Resolve assets" count={queue.counts.unresolved_asset} selected={queue.selected_blocker === "unresolved_asset"} onSelect={onSelect} />
      <ReviewSummary blocker="unsupported_transaction" label="Unsupported or invalid" count={queue.counts.unsupported_transaction} selected={queue.selected_blocker === "unsupported_transaction"} onSelect={onSelect} />
      <ReviewSummary blocker="ready_to_import" label="Ready to import" count={queue.counts.ready_to_import} selected={queue.selected_blocker === "ready_to_import"} onSelect={onSelect} />
    </div>
    {resolver && selectedItem ? <BrokerResolverContext item={selectedItem} resolver={resolver} searchParams={searchParams} /> : null}
    <div className="broker-review-heading">
      <div><strong>{reviewBlockerLabel(queue.selected_blocker)}</strong><span>{queue.account_filter ? "Scoped to one brokerage account" : "Across all brokerage accounts"}</span></div>
      <span>Showing {pageStart}–{pageEnd} of {queue.total}</span>
    </div>
    <div className="broker-review-list">
      {queue.items.map((item) => <BrokerReviewRow key={item.provider_transaction_id} item={item} searchParams={searchParams} />)}
      {!queue.items.length ? <EmptyRow text="No activity matches this review blocker." /> : null}
    </div>
    <div className="broker-review-pagination" aria-label="Review queue pagination">
      <button type="button" onClick={() => onPage(Math.max(0, queue.offset - queue.limit))} disabled={!queue.offset}>Previous</button>
      <span>{pageStart}–{pageEnd} of {queue.total}</span>
      <button type="button" onClick={() => onPage(queue.offset + queue.limit)} disabled={!queue.has_more}>Next</button>
    </div>
  </div>;
}

function ReviewSummary({ blocker, label, count, selected, onSelect }: { blocker: BrokerReviewBlocker; label: string; count: number; selected: boolean; onSelect: (blocker: BrokerReviewBlocker) => void }) {
  return <button type="button" className={selected ? "selected" : ""} aria-pressed={selected} onClick={() => onSelect(blocker)}><span>{label}</span><strong>{count}</strong><em>Open queue</em></button>;
}

function BrokerReviewRow({ item, searchParams }: { item: BrokerReviewQueueItem; searchParams: URLSearchParams }) {
  return <article>
    <div className="broker-review-row-main">
      <InstrumentIdentity instrument={item.instrument} fallback="Unsupported instrument" />
      <StatusPill label={transactionCategoryLabel(item.status)} tone={item.blocker === "ready_to_import" ? "ok" : "warn"} />
    </div>
    <span>{item.institution_name ?? "Broker"} · {item.account_name ?? maskAccount(item.masked_account_number)} · {item.trade_date}</span>
    <p>{item.normalization_result}</p>
    <div className="broker-review-row-actions">
      {item.blocker === "unassigned_account" ? <Link className="button-link" to={accountResolutionUrl(item)}>Assign this account</Link> : null}
      {item.blocker === "unresolved_asset" ? <Link className="button-link" to={reviewResolutionUrl(searchParams, item, "asset")}>Open asset resolver</Link> : null}
      {item.blocker === "unsupported_transaction" ? <Link className="button-link" to={reviewResolutionUrl(searchParams, item, "activity")}>Review why blocked</Link> : null}
      {item.blocker === "ready_to_import" ? <a className="button-link" href="#broker-import-scope">Review import scope</a> : null}
    </div>
  </article>;
}

function BrokerResolverContext({ item, resolver, searchParams }: { item: BrokerReviewQueueItem; resolver: string; searchParams: URLSearchParams }) {
  const symbol = item.instrument.symbol ?? "";
  const candidates = useQuery({ queryKey: ["broker-asset-resolver", symbol], queryFn: () => api.assets(symbol, 8), enabled: resolver === "asset" && Boolean(symbol) });
  const returnPath = `/brokers?${withoutResolver(searchParams).toString()}`;
  return <section className="broker-resolver-context" aria-labelledby="broker-resolver-heading">
    <div><p className="eyebrow">Scoped resolver</p><h3 id="broker-resolver-heading">{resolver === "asset" ? "Verify the local asset candidate" : "Unsupported activity review"}</h3></div>
    <p><strong>{item.institution_name ?? "Broker"} · {item.account_name ?? maskAccount(item.masked_account_number)}</strong><br />Transaction {shortReference(item.provider_transaction_id)} · {item.trade_date} · {transactionCategoryLabel(item.category)}</p>
    {resolver === "asset" ? <>
      <p>This read-only step checks the normalized symbol against the local asset catalog. Broker asset assignment remains governed by the existing normalization and refresh workflow.</p>
      {candidates.isLoading ? <Loading compact /> : candidates.data?.length ? <div className="broker-resolver-candidates">{candidates.data.map((candidate) => <Link key={candidate.asset_id} to={`/asset/${encodeURIComponent(candidate.asset_id)}?from=${encodeURIComponent(returnPath)}`}><Search size={16} /><span><strong>{candidate.symbol}</strong>{candidate.name ?? candidate.asset_id}</span></Link>)}</div> : <div className="broker-warning"><AlertTriangle size={17} /><span>No matching local asset is available. Refresh broker/catalog data; this transaction stays excluded until normalization supplies a stable local asset.</span></div>}
    </> : <p>This transaction is retained for review but excluded from import because its activity type or required values are unsupported. No data was changed.</p>}
    <Link className="broker-inline-link" to={returnPath}>Close resolver</Link>
  </section>;
}

function accountResolutionUrl(item: BrokerReviewQueueItem) {
  const query = new URLSearchParams({ tab: "accounts", account: item.provider_account_id, from: "review", transaction: item.provider_transaction_id });
  return `/brokers?${query.toString()}#${accountAnchor(item.provider_account_id)}`;
}

function reviewResolutionUrl(current: URLSearchParams, item: BrokerReviewQueueItem, resolver: "asset" | "activity") {
  const query = new URLSearchParams(current);
  query.set("tab", "import");
  query.set("queue", item.blocker);
  query.set("account", item.provider_account_id);
  query.set("transaction", item.provider_transaction_id);
  query.set("resolver", resolver);
  return `/brokers?${query.toString()}`;
}

function withoutResolver(current: URLSearchParams) {
  const query = new URLSearchParams(current);
  query.delete("transaction");
  query.delete("resolver");
  return query;
}

function reviewBlockerLabel(blocker: BrokerReviewBlocker) {
  return ({ unassigned_account: "Accounts requiring assignment", unresolved_asset: "Assets requiring resolution", unsupported_transaction: "Unsupported or invalid activity", ready_to_import: "Eligible activity" })[blocker];
}

function ReconciliationTable({ items }: { items: BrokerReconciliationItem[] }) {
  if (!items.length) return <EmptyRow text="No reconciliation rows match this filter." />;
  return (
    <>
      <div className="broker-reconciliation-scroll">
        <table className="broker-reconciliation-table">
          <thead><tr><th>Account</th><th>Instrument</th><th>Broker qty</th><th>Local qty</th><th>Qty diff</th><th>Broker value</th><th>Local value</th><th>Value diff</th><th>Broker data</th><th>Local ledger</th><th>Status</th></tr></thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={`${item.account_name}-${item.instrument?.local_asset_id ?? item.ticker ?? index}-${item.status}`}>
                <td>{item.institution_name ?? "Broker"}<br /><small>{item.account_name ?? maskAccount(item.masked_account_number)}</small></td>
                <td><InstrumentIdentity instrument={item.instrument} fallback={item.ticker ?? item.asset_id ?? "Unsupported instrument"} /></td>
                <td>{number(item.broker_quantity, 4)}</td>
                <td>{number(item.local_quantity, 4)}</td>
                <td>{number(item.quantity_difference, 4)}</td>
                <td>{money(item.broker_market_value, item.currency ?? "CAD")}</td>
                <td>{money(item.local_market_value, item.currency ?? "CAD")}</td>
                <td>{money(item.value_difference, item.currency ?? "CAD")}</td>
                <td>{item.broker_data_timestamp ?? "Unavailable"}</td>
                <td>{formatTimestamp(item.local_ledger_timestamp)}</td>
                <td><StatusPill label={transactionCategoryLabel(item.status)} tone={item.status === "fully_reconciled" ? "ok" : "warn"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="broker-reconciliation-card-list">
        {items.map((item, index) => <article key={`${item.account_name}-${item.instrument?.local_asset_id ?? item.ticker ?? index}-${item.status}`}>
          <div className="broker-card-title"><InstrumentIdentity instrument={item.instrument} fallback={item.ticker ?? item.asset_id ?? "Unsupported instrument"} /><StatusPill label={transactionCategoryLabel(item.status)} tone={item.status === "fully_reconciled" ? "ok" : "warn"} /></div>
          <span>{item.institution_name ?? "Broker"} · {item.account_name ?? maskAccount(item.masked_account_number)}</span>
          <dl>
            <div><dt>Broker quantity</dt><dd>{number(item.broker_quantity, 4)}</dd></div>
            <div><dt>Local quantity</dt><dd>{number(item.local_quantity, 4)}</dd></div>
            <div><dt>Quantity difference</dt><dd>{number(item.quantity_difference, 4)}</dd></div>
            <div><dt>Value difference</dt><dd>{money(item.value_difference, item.currency ?? "CAD")}</dd></div>
          </dl>
          <small>Broker data {item.broker_data_timestamp ?? "unavailable"} · Local ledger {formatTimestamp(item.local_ledger_timestamp)}</small>
        </article>)}
      </div>
    </>
  );
}

function ImportInstrumentIdentity({ item }: { item: BrokerImportPreviewItem }) {
  const securityActivity = ["buys", "sells", "reinvestments"].includes(item.category);
  if (item.instrument.resolution_status === "unsupported" && !securityActivity) {
    return <strong className="broker-instrument-fallback">Cash activity</strong>;
  }
  return <InstrumentIdentity instrument={item.instrument} fallback={item.symbol ?? "Unsupported instrument"} />;
}

function InstrumentIdentity({ instrument, fallback }: { instrument: BrokerReconciliationItem["instrument"] | undefined; fallback: string }) {
  if (!instrument) return <strong className="broker-instrument-fallback">{fallback}</strong>;
  return <div className="broker-instrument-identity">
    <strong>{instrument.display_label || fallback}</strong>
    <span>{[instrument.exchange, instrument.currency, instrument.local_asset_id ? `Local ${instrument.local_asset_id}` : null].filter(Boolean).join(" · ") || "No market metadata"}</span>
    {instrument.resolution_status !== "resolved" ? <em>{instrument.resolution_status === "unresolved" ? "Needs local asset resolution" : "Unsupported instrument"}</em> : null}
  </div>;
}

function SyncHistoryTab({ history, loading, isBusy, onRefresh }: { history: Awaited<ReturnType<typeof api.brokerSyncHistory>>; loading: boolean; isBusy: boolean; onRefresh: () => void }) {
  return (
    <section className="card broker-history-panel">
      <div className="broker-section-heading">
        <div>
          <p className="eyebrow">Refresh history</p>
          <h2>Broker data refresh runs</h2>
        </div>
        <button onClick={onRefresh} disabled={isBusy}><RefreshCw size={17} />Retry refresh</button>
      </div>
      {loading ? <Loading compact /> : history.length ? (
        <div className="broker-history-list">
          {history.map((item) => (
            <article key={item.sync_run_id}>
              <History />
              <div>
                <strong>{formatTimestamp(item.started_at)}</strong>
                <span>{item.connection_label ?? "Broker profile"} · {item.trigger_type} · {item.duration_seconds == null ? "running" : `${item.duration_seconds.toFixed(1)}s`}</span>
                {item.error_summary ? <ErrorCallout text={item.error_summary} action="Review technical details, then retry refresh." /> : null}
              </div>
              <div className="broker-history-counts">
                <span>{item.accounts_processed} accounts</span>
                <span>{item.positions_stored} positions</span>
                <span>{item.activities_stored} activities</span>
                <StatusPill label={transactionCategoryLabel(item.status)} tone={item.status === "success" ? "ok" : "warn"} />
              </div>
            </article>
          ))}
        </div>
      ) : <EmptyRow text="No broker refresh history is stored yet." />}
    </section>
  );
}

function BrokerSettings({ status, isBusy, onStorageChange, onForceRefresh, onTest }: { status: BrokerStatus | undefined; isBusy: boolean; onStorageChange: (enabled: boolean) => void; onForceRefresh: () => void; onTest: () => void }) {
  return (
    <div className="broker-settings-grid">
      <section className="card">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Privacy controls</p>
            <h2>Detailed provider responses</h2>
            <p>Keeps original broker responses for diagnostics and audit history. Turning this off affects future refreshes only and does not remove data already stored.</p>
          </div>
          <label className="toggle-row">
            <input type="checkbox" checked={status?.raw_payload_storage_enabled ?? true} onChange={(event) => onStorageChange(event.target.checked)} disabled={isBusy} />
            <span>Store detailed provider responses</span>
          </label>
        </div>
        <button disabled title="Backend deletion operation not implemented yet"><EyeOff size={17} />Delete previously stored detailed provider responses</button>
      </section>
      <section className="card">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Scheduled refresh</p>
            <h2>Freshness policy</h2>
            <p>Provider data may be daily-cached and is not necessarily real-time.</p>
          </div>
          <button onClick={onForceRefresh} disabled={isBusy}><RefreshCw size={17} />Manual force-refresh</button>
        </div>
        <div className="broker-fact-grid">
          <Fact label="Scheduled refresh" value={status?.scheduled_refresh_enabled ? "Enabled" : "Disabled"} />
          <Fact label="Freshness window" value={`${status?.freshness_window_hours ?? 1} hours`} />
          <Fact label="Last scheduled run" value={formatTimestamp(status?.last_scheduled_run_at)} />
          <Fact label="Next eligible refresh" value={formatTimestamp(status?.next_eligible_refresh_at)} />
          <Fact label="Maximum users per run" value={status?.max_users_per_run == null ? "Not limited" : String(status.max_users_per_run)} />
        </div>
      </section>
      <section className="card broker-danger-zone">
        <div className="broker-section-heading">
          <div>
            <p className="eyebrow">Advanced and danger zone</p>
            <h2>Provider diagnostics</h2>
            <p>Provider-user secret rotation, local unlinking, provider-side deletion and test disabling stay out of the normal workflow. Provider-side deletion is irreversible and should require typed confirmation when exposed.</p>
          </div>
          <button onClick={onTest} disabled={isBusy}><SlidersHorizontal size={17} />Test configuration</button>
        </div>
        <details className="broker-technical-details">
          <summary>Internal metadata</summary>
          <dl>
            <FactTerm term="Broker profile" detail={status?.broker_profile_status ?? "unknown"} />
            <FactTerm term="Provider" detail={providerLabel(status?.provider ?? "snaptrade")} />
            <FactTerm term="Configuration" detail={status?.configured ? "Ready" : "Missing configuration"} />
          </dl>
        </details>
      </section>
    </div>
  );
}

function StatusPill({ label, tone }: { label: string; tone: "ok" | "warn" }) {
  return <span className={`broker-status-pill ${tone}`}>{tone === "ok" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{label}</span>;
}

function ErrorCallout({ text, action }: { text: string; action: string }) {
  return <div className="broker-error-callout"><AlertTriangle size={16} /><span>{text}</span><strong>{action}</strong></div>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="broker-fact"><span>{label}</span><strong>{value}</strong></div>;
}

function FactTerm({ term, detail }: { term: string; detail: string }) {
  return <><dt>{term}</dt><dd>{detail}</dd></>;
}

function connectionStateLabel(state: BrokerConnectionState) {
  return transactionCategoryLabel(state);
}

function accountStateLabel(state: BrokerAccountState) {
  return transactionCategoryLabel(state);
}

function providerLabel(provider: string) {
  return provider.toLowerCase() === "snaptrade" ? "Broker data provider" : provider;
}

function shortReference(value: string) {
  if (value.length <= 8) return "masked";
  return `...${value.slice(-6)}`;
}

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  Database,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Newspaper,
  Search,
  Settings,
  WalletCards,
  X,
} from "lucide-react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { BenchmarkDetailPage, BenchmarksWorkspacePage } from "./benchmarks";
import {
  AssetDetailPage,
  BrokersPage,
  ComparePage,
  NewsTerminalPage,
  OperationsPage,
  OverviewPage,
  PortfolioDetailPage,
  PortfolioWorkspacePage,
  RouteErrorBoundary,
  RetailSentimentPage,
  SettingsPage,
  SignalDetailPage,
  StockRankingsPage,
  type AppNotification,
  type AppSettings,
} from "./appRoutes";
import { PageFeatureProvider } from "./pageFeatureStore";
import { api } from "./api";

const defaultAppSettings: AppSettings = {
  theme: "dark",
  moverDefault: "8",
  density: "comfortable",
  featureColor: true,
};
const loadAppSettings = (): AppSettings => {
  try {
    const raw = window.localStorage.getItem("quaint_dash_app_settings");
    if (!raw) return defaultAppSettings;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return { ...defaultAppSettings, ...parsed };
  } catch {
    return defaultAppSettings;
  }
};

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [settings, setSettings] = useState<AppSettings>(loadAppSettings);
  const [notification, setNotification] = useState<AppNotification | null>(null);
  const location = useLocation();
  const health = useQuery({
    queryKey: ["operations-health-summary"],
    queryFn: api.operationsHealthSummary,
    refetchInterval: 60_000,
  });
  const notify = (message: string, tone: AppNotification["tone"] = "success") => {
    setNotification({ id: Date.now(), tone, message });
  };
  const updateSettings = (next: Partial<AppSettings>) => {
    setSettings((current) => {
      const updated = { ...current, ...next };
      window.localStorage.setItem("quaint_dash_app_settings", JSON.stringify(updated));
      return updated;
    });
  };
  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme;
  }, [settings.theme]);
  return (
    <PageFeatureProvider>
    <div className={`app-shell ${settings.density === "compact" ? "density-compact" : ""} ${settings.featureColor ? "" : "feature-muted"}`}>
      <aside id="primary-navigation" className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand"><ChartNoAxesCombined size={21} /><span>Quaint Dash</span></div>
        <button type="button" className="mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation" title="Close navigation"><X aria-hidden="true" /></button>
        <nav aria-label="Primary navigation">
          <NavLink to="/" end><LayoutDashboard />Overview</NavLink>
          <NavLink to="/portfolios"><WalletCards />Portfolios</NavLink>
          <NavLink to="/news"><Newspaper />News</NavLink>
          <NavLink to="/retail-sentiment"><MessageSquare />Retail sentiment</NavLink>
          <NavLink to="/signals"><Activity />Signals</NavLink>
          <NavLink to="/compare"><BarChart3 />Compare</NavLink>
          <NavLink to="/benchmarks"><Search />Benchmarks</NavLink>
          <NavLink to="/brokers"><Building2 />Brokers</NavLink>
          <NavLink to="/operations"><Database />Operations</NavLink>
          <NavLink to="/settings"><Settings />Settings</NavLink>
        </nav>
        <Link className={`sidebar-note sidebar-health ${health.data?.status ?? (health.error ? "unavailable" : "loading")}`} to={health.data?.operations_url ?? "/operations#operations-health"}>
          <span className="status-dot" />
          <span><strong>{health.isLoading ? "Checking data status" : health.error ? "Data status unavailable" : health.data?.headline ?? "Data status unavailable"}</strong><small>{health.data ? `${health.data.incident_count} active incident${health.data.incident_count === 1 ? "" : "s"}` : "Open Operations"}</small></span>
        </Link>
      </aside>
      <main>
        <header>
          <button type="button" className="mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation" title="Open navigation" aria-controls="primary-navigation" aria-expanded={menuOpen}><Menu aria-hidden="true" /></button>
          <div><p className="eyebrow">Personal finance workspace</p><strong>Investment dashboard</strong></div>
          <div className="avatar">CP</div>
        </header>
        <RouteErrorBoundary key={location.pathname}>
          <Routes>
            <Route path="/" element={<OverviewPage moverDefault={settings.moverDefault} />} />
            <Route path="/portfolios" element={<PortfolioWorkspacePage />} />
            <Route path="/portfolios/:portfolioId" element={<PortfolioDetailPage />} />
            <Route path="/news" element={<NewsTerminalPage />} />
            <Route path="/retail-sentiment" element={<RetailSentimentPage />} />
            <Route path="/signals" element={<StockRankingsPage notify={notify} />} />
            <Route path="/signals/:signalId" element={<SignalDetailPage notify={notify} />} />
            <Route path="/compare-" element={<Navigate to={`/compare${location.search}`} replace />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/benchmarks" element={<BenchmarksWorkspacePage notify={notify} />} />
            <Route path="/benchmarks/:benchmarkId" element={<BenchmarkDetailPage notify={notify} />} />
            <Route path="/assets/:assetId" element={<AssetDetailPage notify={notify} />} />
            <Route path="/asset/:assetId" element={<AssetDetailPage notify={notify} />} />
            <Route path="/brokers" element={<BrokersPage notify={notify} />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/settings" element={<SettingsPage settings={settings} onChange={updateSettings} />} />
          </Routes>
        </RouteErrorBoundary>
        <ActionNotification notification={notification} onClose={() => setNotification(null)} />
      </main>
    </div>
    </PageFeatureProvider>
  );
}

function ActionNotification({ notification, onClose }: { notification: AppNotification | null; onClose: () => void }) {
  useEffect(() => {
    if (!notification) return undefined;
    const timer = window.setTimeout(onClose, 3600);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  if (!notification) return null;
  return (
    <div className={`action-toast ${notification.tone}`} role="status" aria-live="polite">
      {notification.tone === "success" ? <CheckCircle2 size={18} /> : <X size={18} />}
      <span>{notification.message}</span>
      <button aria-label="Dismiss notification" onClick={onClose}><X size={14} /></button>
    </div>
  );
}

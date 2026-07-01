import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  Database,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  WalletCards,
  X,
} from "lucide-react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { BenchmarkDetailPage, BenchmarksWorkspacePage } from "./benchmarks";
import {
  AssetDetailPage,
  BrokersPage,
  ComparePage,
  OperationsPage,
  OverviewPage,
  PortfolioDetailPage,
  PortfolioWorkspacePage,
  RouteErrorBoundary,
  SettingsPage,
  SignalDetailPage,
  StockRankingsPage,
  type AppNotification,
  type AppSettings,
} from "./appRoutes";
import { PageFeatureProvider } from "./pageFeatureStore";

const defaultAppSettings: AppSettings = {
  theme: "light",
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
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand"><ChartNoAxesCombined size={21} /><span>Quaint Dash</span></div>
        <button className="mobile-close" onClick={() => setMenuOpen(false)}><X /></button>
        <nav>
          <NavLink to="/" end><LayoutDashboard />Overview</NavLink>
          <NavLink to="/portfolios"><WalletCards />Portfolios</NavLink>
          <NavLink to="/signals"><Activity />Signals</NavLink>
          <NavLink to="/compare"><BarChart3 />Compare</NavLink>
          <NavLink to="/benchmarks"><Search />Benchmarks</NavLink>
          <NavLink to="/brokers"><Building2 />Brokers</NavLink>
          <NavLink to="/operations"><Database />Operations</NavLink>
          <NavLink to="/settings"><Settings />Settings</NavLink>
        </nav>
        <div className="sidebar-note"><span className="status-dot" />Local API connected</div>
      </aside>
      <main>
        <header>
          <button className="mobile-menu" onClick={() => setMenuOpen(true)}><Menu /></button>
          <div><p className="eyebrow">Personal finance workspace</p><strong>Investment dashboard</strong></div>
          <div className="avatar">CP</div>
        </header>
        <RouteErrorBoundary key={location.pathname}>
          <Routes>
            <Route path="/" element={<OverviewPage moverDefault={settings.moverDefault} />} />
            <Route path="/portfolios" element={<PortfolioWorkspacePage />} />
            <Route path="/portfolios/:portfolioId" element={<PortfolioDetailPage />} />
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

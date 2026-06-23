import { Component, type ReactNode } from "react";
import { ErrorPanel } from "./routes/routeShared";

export type { AppNotification, AppSettings, MoverDefault } from "./routes/routeTypes";

export class RouteErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <div className="page"><ErrorPanel error={this.state.error} /></div>;
    }
    return this.props.children;
  }
}

export { OverviewPage } from "./routes/overviewRoute";

export { SignalDetailPage, StockRankingsPage } from "./routes/signalsRoute";

export { PortfolioDetailPage, PortfolioWorkspacePage } from "./routes/portfolioRoute";
export { AssetDetailPage } from "./routes/assetRoute";

export { ComparePage } from "./routes/compareRoute";

export { SettingsPage } from "./routes/settingsRoute";


export { BrokersPage } from "./routes/brokersRoute";

export { OperationsPage } from "./routes/operationsRoute";

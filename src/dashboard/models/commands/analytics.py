"""Analytics report and optional snapshot-storage commands."""

from dashboard.analytics import AnalyticsEngine, AnalyticsRepository, AnalyticsStorageService


class AnalyticsCommands:
    def asset_analytics_report(self, asset_id: str, benchmark_index_id: str | None = None):
        """
        Build an analytics report for one asset using already stored data.
        """
        repo = AnalyticsRepository(self.conn)
        return AnalyticsEngine(repo).asset_report(
            asset_id=asset_id,
            benchmark_index_id=benchmark_index_id,
        )

    def portfolio_analytics_report(self, portfolio_id: int, benchmark_index_id: str | None = None):
        """
        Build an analytics report for one portfolio using already stored data.
        """
        repo = AnalyticsRepository(self.conn)
        return AnalyticsEngine(repo).portfolio_report(
            portfolio_id=portfolio_id,
            benchmark_index_id=benchmark_index_id,
        )

    def analytics_storage_enabled(self) -> bool:
        repo = AnalyticsRepository(self.conn)
        if not repo._table_exists("analytics_storage_config"):
            return False
        row = self.conn.execute(
            """
            SELECT config_value
            FROM analytics_storage_config
            WHERE config_key = 'enabled'
            """
        ).fetchone()
        return bool(row and str(row[0]).lower() == "true")

    def set_analytics_storage_enabled(self, enabled: bool) -> None:
        AnalyticsStorageService(
            self.conn,
            enabled=self.analytics_storage_enabled(),
        ).set_enabled(enabled)

    def refresh_analytics_storage(
        self,
        asset_ids: list[str] | None = None,
        portfolio_ids: list[int] | None = None,
        benchmark_index_id: str | None = None,
    ):
        return AnalyticsStorageService(
            self.conn,
            enabled=self.analytics_storage_enabled(),
            benchmark_index_id=benchmark_index_id,
        ).refresh_due(
            asset_ids=asset_ids,
            portfolio_ids=portfolio_ids,
        )

    #######################################################################
    ##              read-only broker account linking
    #######################################################################

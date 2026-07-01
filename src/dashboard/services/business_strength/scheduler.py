"""Best-effort scheduler helpers for Business Strength refreshes."""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.services.business_strength import BusinessStrengthAnalyzer


@dataclass(frozen=True)
class BusinessStrengthRefreshResult:
    refreshed: int
    skipped: int
    failures: list[str]


class BusinessStrengthScheduler:
    """Detect stale or missing scorecards and refresh them without blocking core flows."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def refresh_due(self, *, max_assets: int = 25, force: bool = False) -> BusinessStrengthRefreshResult:
        rows = self.conn.execute(
            """
            SELECT a.asset_id
            FROM asset a
            LEFT JOIN (
                SELECT asset_id, max(created_at) AS latest_run_at
                FROM business_strength_analysis_run
                WHERE status IN ('complete', 'insufficient_data')
                GROUP BY asset_id
            ) r ON r.asset_id = a.asset_id
            WHERE COALESCE(a.asset_type, 'stock') IN ('stock', 'equity')
              AND a.track = TRUE
              AND (? OR r.latest_run_at IS NULL OR r.latest_run_at < now() - INTERVAL 14 DAY)
            ORDER BY a.asset_id
            LIMIT ?
            """,
            [force, max_assets],
        ).fetchall()
        analyzer = BusinessStrengthAnalyzer(self.conn)
        refreshed = 0
        failures: list[str] = []
        for (asset_id,) in rows:
            try:
                analyzer.run(asset_id)
                refreshed += 1
            except Exception as exc:
                failures.append(f"{asset_id}: {exc}")
        return BusinessStrengthRefreshResult(refreshed=refreshed, skipped=max(0, max_assets - len(rows)), failures=failures)

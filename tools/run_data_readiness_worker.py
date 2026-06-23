"""Run portfolio data-readiness cycles against a dashboard database."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from threading import Lock

from dashboard.api.data_readiness_background import DataReadinessConfig, DataReadinessWorker
from dashboard.db.db_conn import DB, init_db


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/persistent_db.db")
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--max-assets", type=int, default=200)
    parser.add_argument("--max-jobs", type=int, default=25)
    parser.add_argument("--max-batches", type=int, default=20)
    parser.add_argument("--list-targets", action="store_true")
    args = parser.parse_args()

    if args.list_targets:
        db = DB(Path(args.db))
        init_db(db)
        rows = db.conn.execute(
            """
            SELECT a.asset_id, a.symbol, a.asset_type, a.asset_subtype, a.name, a.description
            FROM portfolio_ticker pt
            JOIN asset a ON a.asset_id = pt.asset_id
            WHERE pt.is_active = TRUE
            ORDER BY a.asset_id
            """
        ).fetchall()
        for row in rows:
            print(row)
        db.conn.close()
        return

    worker = DataReadinessWorker(
        Path(args.db),
        Lock(),
        DataReadinessConfig(
            enabled=True,
            max_assets_per_tick=args.max_assets,
            max_jobs_per_batch=args.max_jobs,
            max_run_batches_per_tick=args.max_batches,
        ),
    )
    result = {}
    for cycle in range(1, args.cycles + 1):
        result = await worker.tick()
        print(f"cycle={cycle} result={result}")
        if (
            result["targets"] == result["ready"] == result["valuations"]
            and result["pending_jobs"] == 0
        ):
            break
    print(f"status={worker.status()}")


if __name__ == "__main__":
    asyncio.run(_main())

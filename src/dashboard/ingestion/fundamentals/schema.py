def ensure_fundamental_phase1_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamental_subscription (
            asset_id TEXT PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,

            refresh_interval_days INTEGER NOT NULL DEFAULT 7,
            next_refresh_at TIMESTAMP,

            last_refresh_attempted_at TIMESTAMP,
            last_refresh_succeeded_at TIMESTAMP,

            last_backfill_requested_at TIMESTAMP,
            last_backfill_succeeded_at TIMESTAMP,

            subscription_source VARCHAR NOT NULL DEFAULT 'manual',

            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamental_sync_state (
            asset_id TEXT NOT NULL,
            dataset VARCHAR NOT NULL,
            sync_mode VARCHAR NOT NULL,

            status VARCHAR NOT NULL,
            last_attempted_at TIMESTAMP,
            last_succeeded_at TIMESTAMP,
            error_message VARCHAR,
            source VARCHAR,

            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),

            PRIMARY KEY (asset_id, dataset, sync_mode)
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fundamental_subscription_due
        ON fundamental_subscription (is_active, next_refresh_at);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fundamental_sync_state_asset
        ON fundamental_sync_state (asset_id);
        """
    )

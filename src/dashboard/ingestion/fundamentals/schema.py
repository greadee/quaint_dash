def ensure_fundamental_phase1_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamental_subscription (
            asset_id TEXT NOT NULL,
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
        ALTER TABLE fundamental_subscription
        ADD COLUMN IF NOT EXISTS last_backfill_requested_at TIMESTAMP;
        """
    )

    conn.execute(
        """
        ALTER TABLE fundamental_subscription
        ADD COLUMN IF NOT EXISTS last_backfill_succeeded_at TIMESTAMP;
        """
    )

    _ensure_mutable_subscription_heap(conn)

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
        CREATE INDEX IF NOT EXISTS idx_fundamental_sync_state_asset
        ON fundamental_sync_state (asset_id);
        """
    )


def _ensure_mutable_subscription_heap(conn) -> None:
    """Remove DuckDB indexes from the frequently updated subscription table."""
    conn.execute("DROP INDEX IF EXISTS idx_fundamental_subscription_due")
    constraint_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM duckdb_constraints()
            WHERE table_name = 'fundamental_subscription'
              AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
            """
        ).fetchone()[0]
    )
    if constraint_count == 0:
        return

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            "ALTER TABLE fundamental_subscription RENAME TO fundamental_subscription_indexed"
        )
        conn.execute(
            """
            CREATE TABLE fundamental_subscription (
                asset_id TEXT NOT NULL,
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
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fundamental_subscription
            SELECT
                asset_id,
                is_active,
                refresh_interval_days,
                next_refresh_at,
                last_refresh_attempted_at,
                last_refresh_succeeded_at,
                last_backfill_requested_at,
                last_backfill_succeeded_at,
                subscription_source,
                created_at,
                updated_at
            FROM (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY asset_id
                        ORDER BY updated_at DESC, created_at DESC
                    ) AS row_number
                FROM fundamental_subscription_indexed
            )
            WHERE row_number = 1
            """
        )
        conn.execute("DROP TABLE fundamental_subscription_indexed")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

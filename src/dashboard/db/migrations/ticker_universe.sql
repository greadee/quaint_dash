CREATE TABLE IF NOT EXISTS portfolio_ticker (
    portfolio_id BIGINT NOT NULL,
    asset_id TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'position',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (portfolio_id, asset_id)
);

CREATE TABLE IF NOT EXISTS watchlist_ticker (
    asset_id TEXT PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

INSERT INTO portfolio_ticker (
    portfolio_id,
    asset_id,
    is_active,
    source,
    created_at,
    updated_at
)
SELECT DISTINCT
    portfolio_id,
    asset_id,
    TRUE,
    'position',
    now(),
    now()
FROM position
WHERE asset_id IS NOT NULL
  AND COALESCE(qty, 0) <> 0
ON CONFLICT (portfolio_id, asset_id)
DO UPDATE SET
    is_active = TRUE,
    updated_at = now();

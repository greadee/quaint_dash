BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS benchmark_index (
    index_id TEXT PRIMARY KEY,
    index_name TEXT NOT NULL,
    index_family TEXT NOT NULL,          -- S&P, Nasdaq, FTSE, MSCI, Nikkei, etc.
    index_category TEXT NOT NULL,        -- core_geo, sector, industry, theme
    region TEXT,
    country_code TEXT,
    currency TEXT NOT NULL,

    is_core BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS benchmark_index_symbol (
    index_id TEXT NOT NULL,
    provider TEXT NOT NULL,              -- fmp, yfinance, finnhub, msci_factsheet, etf_proxy
    provider_symbol TEXT NOT NULL,
    symbol_purpose TEXT NOT NULL,        -- price_daily, price_intraday, constituents, exposure, proxy_price, proxy_holdings
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, provider, provider_symbol, symbol_purpose),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_daily_price (
    index_id TEXT NOT NULL,
    price_date DATE NOT NULL,

    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE NOT NULL,
    adj_close DOUBLE,
    volume DOUBLE,

    previous_close DOUBLE,
    price_return_1d DOUBLE,
    total_return_1d DOUBLE,

    source TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, price_date),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_intraday_price (
    index_id TEXT NOT NULL,
    interval TEXT NOT NULL,              -- 1min, 5min, 15min, 1hour
    bar_start_utc TIMESTAMP NOT NULL,

    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE,

    source TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, interval, bar_start_utc),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_composition_snapshot (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,

    source TEXT NOT NULL,
    source_symbol TEXT,
    source_type TEXT NOT NULL,           -- official_api, provider_api, factsheet, etf_proxy, manual_seed
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,

    constituent_count INTEGER,
    total_weight_pct DOUBLE,
    data_quality TEXT NOT NULL DEFAULT 'unknown', -- exact, approximate, proxy, partial, unknown
    notes TEXT,

    fetched_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, snapshot_date, source),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_constituent (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    source TEXT NOT NULL,

    constituent_symbol TEXT NOT NULL,
    constituent_name TEXT,
    exchange_code TEXT,
    country_code TEXT,
    currency TEXT,
    sector TEXT,
    industry TEXT,

    weight_pct DOUBLE,
    market_cap DOUBLE,
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (
        index_id,
        snapshot_date,
        source,
        constituent_symbol
    ),

    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_exposure_snapshot (
    index_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,

    dimension_type TEXT NOT NULL,        -- country, region, sector, industry, currency
    dimension_value TEXT NOT NULL,
    weight_pct DOUBLE NOT NULL,

    source TEXT NOT NULL,
    source_type TEXT NOT NULL,           -- computed_from_constituents, factsheet, etf_proxy
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,

    fetched_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (
        index_id,
        snapshot_date,
        dimension_type,
        dimension_value,
        source
    ),

    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_daily_metric (
    index_id TEXT NOT NULL,
    metric_date DATE NOT NULL,

    return_1d DOUBLE,
    return_5d DOUBLE,
    return_21d DOUBLE,
    return_63d DOUBLE,
    return_126d DOUBLE,
    return_252d DOUBLE,
    return_ytd DOUBLE,

    volatility_21d_ann DOUBLE,
    volatility_63d_ann DOUBLE,
    volatility_252d_ann DOUBLE,

    sma_50 DOUBLE,
    sma_200 DOUBLE,

    high_52w DOUBLE,
    low_52w DOUBLE,
    drawdown_from_52w_high DOUBLE,

    source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, metric_date),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_relative_metric (
    index_id TEXT NOT NULL,
    comparison_index_id TEXT NOT NULL,
    metric_date DATE NOT NULL,

    correlation_252d DOUBLE,
    beta_252d DOUBLE,
    excess_return_252d DOUBLE,

    source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, comparison_index_id, metric_date),

    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id),
    FOREIGN KEY (comparison_index_id) REFERENCES benchmark_index(index_id)
);

CREATE TABLE IF NOT EXISTS benchmark_index_sync_state (
    index_id TEXT NOT NULL,
    job_type TEXT NOT NULL,              -- daily_price, intraday_price, composition, exposure, metrics

    last_success_at TIMESTAMP,
    last_attempt_at TIMESTAMP,
    last_success_date DATE,
    last_error TEXT,

    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (index_id, job_type),
    FOREIGN KEY (index_id) REFERENCES benchmark_index(index_id)
);

COMMIT;
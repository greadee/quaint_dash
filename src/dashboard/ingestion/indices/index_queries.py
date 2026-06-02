UPSERT_BENCHMARK_INDEX = """
INSERT INTO benchmark_index (
    index_id,
    index_name,
    index_family,
    index_category,
    region,
    country_code,
    currency,
    is_core,
    is_active,
    notes,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?, now())
ON CONFLICT (index_id) DO UPDATE SET
    index_name = excluded.index_name,
    index_family = excluded.index_family,
    index_category = excluded.index_category,
    region = excluded.region,
    country_code = excluded.country_code,
    currency = excluded.currency,
    is_core = excluded.is_core,
    is_active = excluded.is_active,
    notes = excluded.notes,
    updated_at = now();
"""

UPSERT_BENCHMARK_INDEX_SYMBOL = """
INSERT INTO benchmark_index_symbol (
    index_id,
    provider,
    provider_symbol,
    symbol_purpose,
    is_primary,
    is_proxy,
    updated_at
)
VALUES (?, ?, ?, ?, ?, ?, now())
ON CONFLICT (index_id, provider, provider_symbol, symbol_purpose) DO UPDATE SET
    is_primary = excluded.is_primary,
    is_proxy = excluded.is_proxy,
    updated_at = now();
"""

GET_PRIMARY_SYMBOL = """
SELECT
    index_id,
    provider,
    provider_symbol,
    symbol_purpose,
    is_primary,
    is_proxy
FROM benchmark_index_symbol
WHERE index_id = ?
  AND symbol_purpose IN (?, ?)
ORDER BY
    is_primary DESC,
    is_proxy ASC,
    provider ASC
LIMIT 1;
"""

GET_ALL_SYMBOLS_FOR_PURPOSE = """
SELECT
    index_id,
    provider,
    provider_symbol,
    symbol_purpose,
    is_primary,
    is_proxy
FROM benchmark_index_symbol
WHERE index_id = ?
  AND symbol_purpose IN (?, ?)
ORDER BY
    is_primary DESC,
    is_proxy ASC,
    provider ASC;
"""

GET_CORE_INDICES = """
SELECT index_id
FROM benchmark_index
WHERE is_core = TRUE
  AND is_active = TRUE
ORDER BY index_id;
"""

UPSERT_DAILY_PRICE = """
INSERT INTO benchmark_index_daily_price (
    index_id,
    price_date,
    open,
    high,
    low,
    close,
    adj_close,
    volume,
    previous_close,
    price_return_1d,
    total_return_1d,
    source,
    source_symbol,
    is_proxy,
    fetched_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (index_id, price_date) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    adj_close = excluded.adj_close,
    volume = excluded.volume,
    previous_close = excluded.previous_close,
    price_return_1d = excluded.price_return_1d,
    total_return_1d = excluded.total_return_1d,
    source = excluded.source,
    source_symbol = excluded.source_symbol,
    is_proxy = excluded.is_proxy,
    fetched_at = now();
"""

GET_DAILY_CLOSES = """
SELECT price_date, close
FROM benchmark_index_daily_price
WHERE index_id = ?
ORDER BY price_date;
"""

GET_DAILY_CLOSES_TO_DATE = """
SELECT price_date, close
FROM benchmark_index_daily_price
WHERE index_id = ?
  AND price_date <= ?
ORDER BY price_date;
"""

UPSERT_INTRADAY_PRICE = """
INSERT INTO benchmark_index_intraday_price (
    index_id,
    interval,
    bar_start_utc,
    open,
    high,
    low,
    close,
    volume,
    source,
    source_symbol,
    is_proxy,
    fetched_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (index_id, interval, bar_start_utc) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    source = excluded.source,
    source_symbol = excluded.source_symbol,
    is_proxy = excluded.is_proxy,
    fetched_at = now();
"""

UPSERT_COMPOSITION_SNAPSHOT = """
INSERT INTO benchmark_index_composition_snapshot (
    index_id,
    snapshot_date,
    source,
    source_symbol,
    source_type,
    is_proxy,
    constituent_count,
    total_weight_pct,
    data_quality,
    notes,
    fetched_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
ON CONFLICT (index_id, snapshot_date, source) DO UPDATE SET
    source_symbol = excluded.source_symbol,
    source_type = excluded.source_type,
    is_proxy = excluded.is_proxy,
    constituent_count = excluded.constituent_count,
    total_weight_pct = excluded.total_weight_pct,
    data_quality = excluded.data_quality,
    notes = excluded.notes,
    fetched_at = now();
"""

DELETE_CONSTITUENTS_FOR_SNAPSHOT_SOURCE = """
DELETE FROM benchmark_index_constituent
WHERE index_id = ?
  AND snapshot_date = ?
  AND source = ?;
"""

INSERT_CONSTITUENT = """
INSERT INTO benchmark_index_constituent (
    index_id,
    snapshot_date,
    source,
    constituent_symbol,
    constituent_name,
    exchange_code,
    country_code,
    currency,
    sector,
    industry,
    weight_pct,
    market_cap,
    is_proxy
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

DELETE_EXPOSURES_FOR_SNAPSHOT = """
DELETE FROM benchmark_index_exposure_snapshot
WHERE index_id = ?
  AND snapshot_date = ?;
"""

INSERT_EXPOSURE = """
INSERT INTO benchmark_index_exposure_snapshot (
    index_id,
    snapshot_date,
    dimension_type,
    dimension_value,
    weight_pct,
    source,
    source_type,
    is_proxy,
    fetched_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, now());
"""

UPSERT_DAILY_METRIC = """
INSERT INTO benchmark_index_daily_metric (
    index_id,
    metric_date,
    return_1d,
    return_5d,
    return_21d,
    return_63d,
    return_126d,
    return_252d,
    return_ytd,
    volatility_21d_ann,
    volatility_63d_ann,
    volatility_252d_ann,
    sma_50,
    sma_200,
    high_52w,
    low_52w,
    drawdown_from_52w_high,
    source,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'computed', now())
ON CONFLICT (index_id, metric_date) DO UPDATE SET
    return_1d = excluded.return_1d,
    return_5d = excluded.return_5d,
    return_21d = excluded.return_21d,
    return_63d = excluded.return_63d,
    return_126d = excluded.return_126d,
    return_252d = excluded.return_252d,
    return_ytd = excluded.return_ytd,
    volatility_21d_ann = excluded.volatility_21d_ann,
    volatility_63d_ann = excluded.volatility_63d_ann,
    volatility_252d_ann = excluded.volatility_252d_ann,
    sma_50 = excluded.sma_50,
    sma_200 = excluded.sma_200,
    high_52w = excluded.high_52w,
    low_52w = excluded.low_52w,
    drawdown_from_52w_high = excluded.drawdown_from_52w_high,
    source = excluded.source,
    computed_at = now();
"""

UPSERT_RELATIVE_METRIC = """
INSERT INTO benchmark_index_relative_metric (
    index_id,
    comparison_index_id,
    metric_date,
    correlation_252d,
    beta_252d,
    excess_return_252d,
    source,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, 'computed', now())
ON CONFLICT (index_id, comparison_index_id, metric_date) DO UPDATE SET
    correlation_252d = excluded.correlation_252d,
    beta_252d = excluded.beta_252d,
    excess_return_252d = excluded.excess_return_252d,
    source = excluded.source,
    computed_at = now();
"""

UPSERT_SYNC_STATE_SUCCESS = """
INSERT INTO benchmark_index_sync_state (
    index_id,
    job_type,
    last_success_at,
    last_attempt_at,
    last_success_date,
    last_error,
    updated_at
)
VALUES (?, ?, now(), now(), ?, NULL, now())
ON CONFLICT (index_id, job_type) DO UPDATE SET
    last_success_at = now(),
    last_attempt_at = now(),
    last_success_date = excluded.last_success_date,
    last_error = NULL,
    updated_at = now();
"""

UPSERT_SYNC_STATE_FAILURE = """
INSERT INTO benchmark_index_sync_state (
    index_id,
    job_type,
    last_attempt_at,
    last_error,
    updated_at
)
VALUES (?, ?, now(), ?, now())
ON CONFLICT (index_id, job_type) DO UPDATE SET
    last_attempt_at = now(),
    last_error = excluded.last_error,
    updated_at = now();
"""
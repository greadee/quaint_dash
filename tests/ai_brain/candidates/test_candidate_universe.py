from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dashboard.ai_brain.candidates import (
    CandidateSourceAdapters,
    OutsideHoldingUniverseBuilder,
    canonical_hash,
)
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 8, 4, 12, 0)
SNAPSHOT_DATE = date(2026, 8, 4)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-universe.db")
    init_db(db)
    db.conn.execute(
        "INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Primary')"
    )
    db.conn.execute(
        "INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')"
    )
    yield db.conn
    db.conn.close()


def _asset(
    conn,
    asset_id: str,
    *,
    symbol: str | None = None,
    subtype: str | None = None,
    name: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, asset_subtype, ccy, name,
            created_at, updated_at
        )
        VALUES (?, ?, 'stock', ?, 'USD', ?, ?, ?)
        """,
        [asset_id, symbol or asset_id, subtype, name or asset_id, UPDATED_AT, UPDATED_AT],
    )


def _hold(conn, asset_id: str, *, quantity: float = 1.0) -> None:
    conn.execute(
        """
        INSERT INTO txn(
            portfolio_id, time_stamp, txn_type, asset_id, qty, price,
            ccy, cash_amt, batch_id
        )
        VALUES (1, ?, 'buy', ?, ?, 10, 'USD', ?, 1)
        """,
        [UPDATED_AT, asset_id, quantity, -(quantity * 10)],
    )


def _ranking(conn, asset_id: str, *, score: float = 80.0) -> None:
    conn.execute(
        """
        INSERT INTO stock_ranking_snapshot(
            asset_id, factor, snapshot_date, universe, score, action,
            confidence, data_status, latest_data_date, created_at, updated_at
        )
        VALUES (?, 'aggregate', ?, 'all', ?, 'watch', 0.9, 'available', ?, ?, ?)
        """,
        [asset_id, SNAPSHOT_DATE, score, SNAPSHOT_DATE, UPDATED_AT, UPDATED_AT],
    )


def _watch(conn, asset_id: str, *, active: bool = True) -> None:
    conn.execute(
        """
        INSERT INTO watchlist_ticker(
            asset_id, is_active, source, created_at, updated_at
        )
        VALUES (?, ?, 'manual', ?, ?)
        """,
        [asset_id, active, UPDATED_AT, UPDATED_AT],
    )


def _benchmark(
    conn,
    index_id: str,
    constituents: tuple[tuple[str, float], ...],
    *,
    is_proxy: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO benchmark_index(
            index_id, index_name, index_family, index_category, currency,
            created_at, updated_at
        )
        VALUES (?, ?, 'test', 'core_geo', 'USD', ?, ?)
        """,
        [index_id, index_id, UPDATED_AT, UPDATED_AT],
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_composition_snapshot(
            index_id, snapshot_date, source, source_type, is_proxy,
            constituent_count, data_quality, fetched_at
        )
        VALUES (?, ?, 'test', 'manual_seed', ?, ?, ?, ?)
        """,
        [
            index_id,
            SNAPSHOT_DATE,
            is_proxy,
            len(constituents),
            "proxy" if is_proxy else "exact",
            UPDATED_AT,
        ],
    )
    for symbol, weight in constituents:
        conn.execute(
            """
            INSERT INTO benchmark_index_constituent(
                index_id, snapshot_date, source, constituent_symbol,
                weight_pct, is_proxy
            )
            VALUES (?, ?, 'test', ?, ?, ?)
            """,
            [index_id, SNAPSHOT_DATE, symbol, weight, is_proxy],
        )


def test_excludes_direct_held_exposure(conn) -> None:
    _asset(conn, "AAPL")
    _asset(conn, "MSFT")
    _hold(conn, "AAPL")
    _ranking(conn, "AAPL", score=99)
    _ranking(conn, "MSFT", score=90)

    result = OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=AS_OF)

    assert [item.asset_id for item in result.candidates] == ["MSFT"]
    assert [(item.asset_id, item.reason_code) for item in result.exclusions] == [
        ("AAPL", "guardrail.exposure.direct_holding")
    ]


def test_excludes_resolved_cdr_underlying_held_exposure(conn) -> None:
    _asset(conn, "NVDA")
    _asset(
        conn,
        "NVDA.TO",
        symbol="NVDA.TO",
        subtype="cdr",
        name="NVIDIA Canadian depositary receipt",
    )
    _hold(conn, "NVDA.TO")
    _ranking(conn, "NVDA")

    result = OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=AS_OF)

    assert result.candidates == ()
    assert [(item.asset_id, item.reason_code) for item in result.exclusions] == [
        ("NVDA", "guardrail.exposure.equivalent_holding")
    ]


def test_merges_all_source_reasons_and_evidence_deterministically(conn) -> None:
    _asset(conn, "MERGE", name="Merge Systems")
    _ranking(conn, "MERGE")
    _watch(conn, "MERGE")
    _benchmark(conn, "TEST100", (("MERGE", 5.0),))
    adapters = CandidateSourceAdapters(conn)
    sources = (
        adapters.top_ranked(as_of=AS_OF),
        adapters.active_watchlist(as_of=AS_OF),
        adapters.all_universe_search(as_of=AS_OF, search_terms=("merge",)),
        adapters.benchmark_constituents(
            as_of=AS_OF,
            benchmark_index_ids=("TEST100",),
        ),
    )
    builder = OutsideHoldingUniverseBuilder(conn)

    first = builder.build_from_sources(
        portfolio_id=1,
        as_of=AS_OF,
        source_results=sources,
    )
    second = builder.build_from_sources(
        portfolio_id=1,
        as_of=AS_OF,
        source_results=tuple(reversed(sources)),
    )

    assert canonical_hash(first) == canonical_hash(second)
    assert len(first.candidates) == 1
    candidate = first.candidates[0]
    assert candidate.asset_id == "MERGE"
    assert {match.source_family for match in candidate.source_matches} == {
        "all_universe",
        "benchmark",
        "ranking",
        "watchlist",
    }
    assert set(candidate.reason_codes) == {
        "source.all_universe.search",
        "source.benchmark.constituent",
        "source.ranking.aggregate",
        "source.watchlist.active",
    }
    assert len(candidate.evidence_refs) == 4
    assert {
        ref.evidence_id
        for match in candidate.source_matches
        for ref in match.evidence_refs
    } == {ref.evidence_id for ref in candidate.evidence_refs}


def test_adapters_return_deterministic_order_and_proxy_reason(conn) -> None:
    _asset(conn, "ZED")
    _asset(conn, "ALPHA")
    _watch(conn, "ZED")
    _watch(conn, "ALPHA")
    _benchmark(conn, "PROXY", (("ZED", 60), ("ALPHA", 40)), is_proxy=True)
    adapters = CandidateSourceAdapters(conn)

    watchlist = adapters.active_watchlist(as_of=AS_OF)
    benchmark = adapters.benchmark_constituents(
        as_of=AS_OF,
        benchmark_index_ids=("PROXY",),
    )

    assert [item.source_asset_id for item in watchlist.nominations] == ["ALPHA", "ZED"]
    assert [item.source_asset_id for item in benchmark.nominations] == ["ALPHA", "ZED"]
    assert {item.source_match.reason_code for item in benchmark.nominations} == {
        "source.benchmark.proxy_constituent"
    }


def test_unresolved_identity_is_deduplicated_and_blocked(conn) -> None:
    _benchmark(conn, "ONE", (("UNKNOWN", 5),))
    _benchmark(conn, "TWO", (("UNKNOWN", 7),))

    result = OutsideHoldingUniverseBuilder(conn).build(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_ids=("TWO", "ONE"),
    )

    assert result.candidates == ()
    assert len(result.blocked_identities) == 1
    blocked = result.blocked_identities[0]
    assert blocked.source_asset_id == "UNKNOWN"
    assert blocked.reason_code == "guardrail.identity.unresolved"
    assert len(blocked.evidence_refs) == 2
    assert len(blocked.source_matches) == 1
    assert blocked.warnings[0].blocking is True
    assert blocked.warnings[0].severity == "critical"


def test_missing_cdr_underlying_is_blocked(conn) -> None:
    _asset(
        conn,
        "FAKE.TO",
        subtype="cdr",
        name="Fake Canadian depositary receipt",
    )
    _ranking(conn, "FAKE.TO")

    result = OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=AS_OF)

    assert result.candidates == ()
    assert [item.source_asset_id for item in result.blocked_identities] == ["FAKE.TO"]


def test_empty_sources_report_truthful_missing_and_unsupported_metadata(conn) -> None:
    result = OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=AS_OF)
    coverage = {
        watermark.source_domain: watermark.coverage_state
        for watermark in result.source_watermarks
    }

    assert result.candidates == ()
    assert coverage == {
        "asset-business-classification": "unsupported",
        "asset-catalog-search": "unsupported",
        "benchmark-composition": "unsupported",
        "business-strength-peer-groups": "unsupported",
        "portfolio-geography-gap": "unsupported",
        "portfolio-sector-gap": "unsupported",
        "profile-theme-benchmark": "unsupported",
        "stock-ranking": "missing",
        "watchlist": "missing",
    }
    assert set(result.source_limitations) == {
        "source.geography_gap.benchmark_not_supplied",
        "source.industry.seed_not_supplied",
        "source.peer.seed_not_supplied",
        "source.all_universe.query_not_supplied",
        "source.benchmark.index_not_supplied",
        "source.ranking.snapshot_missing",
        "source.sector_gap.benchmark_not_supplied",
        "source.theme.profile_not_supplied",
        "source.watchlist.snapshot_missing",
    }


def test_empty_benchmark_snapshot_reports_missing_constituents(conn) -> None:
    _benchmark(conn, "EMPTY", ())

    result = CandidateSourceAdapters(conn).benchmark_constituents(
        as_of=AS_OF,
        benchmark_index_ids=("EMPTY",),
    )

    assert result.nominations == ()
    assert result.watermark.coverage_state == "missing"
    assert result.watermark.as_of == datetime(2026, 8, 4, tzinfo=timezone.utc)
    assert set(result.limitations) == {
        "source.benchmark.composition_missing",
        "source.benchmark.constituents_missing",
    }


def test_future_current_state_rows_are_not_used(conn) -> None:
    _asset(conn, "FUTURE")
    conn.execute(
        """
        INSERT INTO watchlist_ticker(
            asset_id, is_active, source, created_at, updated_at
        )
        VALUES ('FUTURE', TRUE, 'manual', '2026-08-06', '2026-08-06')
        """
    )

    result = CandidateSourceAdapters(conn).active_watchlist(as_of=AS_OF)

    assert result.nominations == ()
    assert result.watermark.coverage_state == "missing"


def test_future_asset_identity_does_not_resolve_historical_nomination(conn) -> None:
    _asset(conn, "FUTURE")
    conn.execute(
        "UPDATE asset SET updated_at = '2026-08-06' WHERE asset_id = 'FUTURE'"
    )
    _benchmark(conn, "HISTORICAL", (("FUTURE", 10),))

    result = OutsideHoldingUniverseBuilder(conn).build(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_ids=("HISTORICAL",),
    )

    assert result.candidates == ()
    assert [item.source_asset_id for item in result.blocked_identities] == ["FUTURE"]


def test_naive_as_of_is_rejected(conn) -> None:
    naive = datetime(2026, 8, 5, 20, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        CandidateSourceAdapters(conn).top_ranked(as_of=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=naive)

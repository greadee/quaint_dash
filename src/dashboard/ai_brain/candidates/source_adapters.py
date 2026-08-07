"""Read-only adapters from stored source snapshots into candidate nominations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

from dashboard.ai_brain.candidates.canonical import (
    candidate_evidence_id,
    canonical_hash,
)
from dashboard.ai_brain.candidates.models import (
    CandidateEvidenceRef,
    CandidateSourceMatch,
    CandidateSourceWatermark,
)

CANDIDATE_SOURCE_ADAPTER_VERSION = "candidate-source-adapters.v1"
STOCK_RANKING_SCHEMA_VERSION = "stock-ranking-snapshot.v1"
WATCHLIST_SCHEMA_VERSION = "watchlist-ticker.v1"
ALL_UNIVERSE_SCHEMA_VERSION = "asset-catalog-search.v1"
BENCHMARK_CONSTITUENT_SCHEMA_VERSION = "benchmark-constituent.v1"


@dataclass(frozen=True)
class CandidateNomination:
    source_asset_id: str
    ticker: str
    source_match: CandidateSourceMatch

    def __post_init__(self) -> None:
        if not self.source_asset_id or self.source_asset_id != self.source_asset_id.strip():
            raise ValueError("source_asset_id must be nonempty and trimmed")
        if not self.ticker or self.ticker != self.ticker.strip().upper():
            raise ValueError("nomination ticker must be nonempty, trimmed, and uppercase")


@dataclass(frozen=True)
class CandidateNominationBlock:
    source_asset_id: str
    ticker: str
    reason_code: str
    source_match: CandidateSourceMatch

    def __post_init__(self) -> None:
        if not self.source_asset_id or self.source_asset_id != self.source_asset_id.strip():
            raise ValueError("blocked source_asset_id must be nonempty and trimmed")
        if not self.ticker or self.ticker != self.ticker.strip().upper():
            raise ValueError("blocked nomination ticker must be uppercase and trimmed")
        if not self.reason_code.startswith("guardrail.profile."):
            raise ValueError("blocked nominations require a profile guardrail reason")


@dataclass(frozen=True)
class SourceAdapterResult:
    source_family: str
    watermark: CandidateSourceWatermark
    nominations: tuple[CandidateNomination, ...]
    blocked_nominations: tuple[CandidateNominationBlock, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            nomination.source_match.source_family != self.source_family
            for nomination in self.nominations
        ):
            raise ValueError("adapter nominations must match the adapter source family")
        if any(
            nomination.source_match.source_family != self.source_family
            for nomination in self.blocked_nominations
        ):
            raise ValueError("blocked nominations must match the adapter source family")


class CandidateSourceAdapters:
    """Query bounded local snapshots without hydrating or mutating source data."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def top_ranked(
        self,
        *,
        as_of: datetime,
        factor: str = "aggregate",
        universe: str = "all",
        limit: int = 25,
    ) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit("ranking limit", limit)
        normalized_factor = factor.lower().strip()
        normalized_universe = universe.lower().strip()
        if not normalized_factor or not normalized_universe:
            raise ValueError("ranking factor and universe must be nonempty")
        rows = self.conn.execute(
            """
            WITH ranked AS (
                SELECT
                    snapshot.asset_id,
                    COALESCE(asset.symbol, snapshot.asset_id) AS ticker,
                    snapshot.snapshot_date,
                    snapshot.score,
                    snapshot.action,
                    snapshot.confidence,
                    snapshot.data_status,
                    snapshot.latest_data_date,
                    snapshot.components_json,
                    snapshot.missing_inputs_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY snapshot.asset_id
                        ORDER BY snapshot.snapshot_date DESC
                    ) AS snapshot_rank
                FROM stock_ranking_snapshot snapshot
                LEFT JOIN asset
                  ON asset.asset_id = snapshot.asset_id
                 AND asset.updated_at <= ?
                WHERE snapshot.factor = ?
                  AND snapshot.universe = ?
                  AND snapshot.snapshot_date <= ?
            )
            SELECT
                asset_id, ticker, snapshot_date, score, action, confidence,
                data_status, latest_data_date, components_json, missing_inputs_json
            FROM ranked
            WHERE snapshot_rank = 1
            ORDER BY score DESC, confidence DESC, asset_id
            LIMIT ?
            """,
            [
                _as_db_timestamp(as_of),
                normalized_factor,
                normalized_universe,
                as_of.date(),
                limit,
            ],
        ).fetchall()
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=CandidateSourceMatch(
                    source_family="ranking",
                    source_methodology_version=STOCK_RANKING_SCHEMA_VERSION,
                    reason_code=f"source.ranking.{normalized_factor}",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="stock-ranking",
                            source_schema_version=STOCK_RANKING_SCHEMA_VERSION,
                            source_record_id=(
                                f"ranking:{normalized_factor}:{normalized_universe}:"
                                f"{row[2].isoformat()}:{row[0]}"
                            ),
                            as_of=_as_utc(row[2]),
                            payload={
                                "asset_id": row[0],
                                "factor": normalized_factor,
                                "universe": normalized_universe,
                                "snapshot_date": row[2],
                                "score": row[3],
                                "action": row[4],
                                "confidence": row[5],
                                "data_status": row[6],
                                "latest_data_date": row[7],
                                "components_json": row[8],
                                "missing_inputs_json": row[9],
                            },
                        ),
                    ),
                ),
            )
            for row in rows
        )
        watermark_as_of = max(
            (nomination.source_match.evidence_refs[0].as_of for nomination in nominations),
            default=None,
        )
        return SourceAdapterResult(
            source_family="ranking",
            watermark=CandidateSourceWatermark(
                source_domain="stock-ranking",
                source_schema_version=STOCK_RANKING_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state="available" if watermark_as_of else "missing",
            ),
            nominations=nominations,
            limitations=(
                () if watermark_as_of else ("source.ranking.snapshot_missing",)
            ),
        )

    def active_watchlist(self, *, as_of: datetime) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        as_of_db = _as_db_timestamp(as_of)
        rows = self.conn.execute(
            """
            SELECT
                watchlist.asset_id,
                COALESCE(asset.symbol, watchlist.asset_id) AS ticker,
                watchlist.source,
                watchlist.updated_at
            FROM watchlist_ticker watchlist
            LEFT JOIN asset
              ON asset.asset_id = watchlist.asset_id
             AND asset.updated_at <= ?
            WHERE watchlist.is_active = TRUE
              AND watchlist.updated_at <= ?
            ORDER BY watchlist.asset_id
            """,
            [as_of_db, as_of_db],
        ).fetchall()
        source_watermark = self.conn.execute(
            "SELECT MAX(updated_at) FROM watchlist_ticker WHERE updated_at <= ?",
            [as_of_db],
        ).fetchone()[0]
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=CandidateSourceMatch(
                    source_family="watchlist",
                    source_methodology_version=WATCHLIST_SCHEMA_VERSION,
                    reason_code="source.watchlist.active",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="watchlist",
                            source_schema_version=WATCHLIST_SCHEMA_VERSION,
                            source_record_id=f"watchlist:{row[0]}",
                            as_of=_as_utc(row[3]),
                            payload={
                                "asset_id": row[0],
                                "is_active": True,
                                "source": row[2],
                                "updated_at": _as_utc(row[3]),
                            },
                        ),
                    ),
                ),
            )
            for row in rows
        )
        watermark_as_of = _as_utc(source_watermark) if source_watermark else None
        return SourceAdapterResult(
            source_family="watchlist",
            watermark=CandidateSourceWatermark(
                source_domain="watchlist",
                source_schema_version=WATCHLIST_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state="partial" if watermark_as_of else "missing",
            ),
            nominations=nominations,
            limitations=(
                ("source.watchlist.current_state_only",)
                if watermark_as_of
                else ("source.watchlist.snapshot_missing",)
            ),
        )

    def all_universe_search(
        self,
        *,
        as_of: datetime,
        search_terms: tuple[str, ...],
        limit_per_term: int = 25,
    ) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit("all-universe limit", limit_per_term)
        terms = tuple(sorted({term.lower().strip() for term in search_terms if term.strip()}))
        if not terms:
            return SourceAdapterResult(
                source_family="all_universe",
                watermark=CandidateSourceWatermark(
                    source_domain="asset-catalog-search",
                    source_schema_version=ALL_UNIVERSE_SCHEMA_VERSION,
                    as_of=None,
                    coverage_state="unsupported",
                ),
                nominations=(),
                limitations=("source.all_universe.query_not_supplied",),
            )

        nominations: list[CandidateNomination] = []
        for term in terms:
            rows = self._all_universe_rows(
                term=term,
                as_of=as_of,
                limit=limit_per_term,
            )
            for row in rows:
                evidence_as_of = _as_utc(row[8])
                nominations.append(
                    CandidateNomination(
                        source_asset_id=str(row[0]),
                        ticker=str(row[1]).upper(),
                        source_match=CandidateSourceMatch(
                            source_family="all_universe",
                            source_methodology_version=ALL_UNIVERSE_SCHEMA_VERSION,
                            reason_code="source.all_universe.search",
                            evidence_refs=(
                                candidate_source_evidence(
                                    source_domain="asset-catalog-search",
                                    source_schema_version=ALL_UNIVERSE_SCHEMA_VERSION,
                                    source_record_id=f"search:{term}:{row[0]}",
                                    as_of=evidence_as_of,
                                    payload={
                                        "query": term,
                                        "asset_id": row[0],
                                        "symbol": row[1],
                                        "asset_type": row[2],
                                        "currency": row[3],
                                        "name": row[4],
                                        "sector": row[5],
                                        "industry": row[6],
                                        "country": row[7],
                                        "source_table": row[9],
                                    },
                                ),
                            ),
                        ),
                    )
                )
        source_watermark = self.conn.execute(
            """
            SELECT MAX(updated_at)
            FROM (
                SELECT updated_at FROM asset WHERE updated_at <= ?
                UNION ALL
                SELECT updated_at FROM stock_catalog WHERE updated_at <= ?
            )
            """,
            [_as_db_timestamp(as_of), _as_db_timestamp(as_of)],
        ).fetchone()[0]
        watermark_as_of = _as_utc(source_watermark) if source_watermark else None
        return SourceAdapterResult(
            source_family="all_universe",
            watermark=CandidateSourceWatermark(
                source_domain="asset-catalog-search",
                source_schema_version=ALL_UNIVERSE_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state="partial" if watermark_as_of else "missing",
            ),
            nominations=tuple(
                sorted(
                    nominations,
                    key=lambda item: (
                        item.source_asset_id,
                        item.source_match.evidence_refs[0].source_record_id,
                    ),
                )
            ),
            limitations=(
                ("source.all_universe.current_state_only",)
                if watermark_as_of
                else ("source.all_universe.snapshot_missing",)
            ),
        )

    def benchmark_constituents(
        self,
        *,
        as_of: datetime,
        benchmark_index_ids: tuple[str, ...],
        limit_per_index: int = 100,
    ) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit("benchmark constituent limit", limit_per_index)
        index_ids = tuple(
            sorted(
                {
                    value.upper().strip()
                    for value in benchmark_index_ids
                    if value.strip()
                }
            )
        )
        if not index_ids:
            return SourceAdapterResult(
                source_family="benchmark",
                watermark=CandidateSourceWatermark(
                    source_domain="benchmark-composition",
                    source_schema_version=BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
                    as_of=None,
                    coverage_state="unsupported",
                ),
                nominations=(),
                limitations=("source.benchmark.index_not_supplied",),
            )

        nominations: list[CandidateNomination] = []
        covered_indexes = 0
        snapshot_dates: list[date] = []
        for index_id in index_ids:
            snapshot = self.conn.execute(
                """
                SELECT snapshot_date, source, is_proxy, data_quality
                FROM benchmark_index_composition_snapshot
                WHERE UPPER(index_id) = ?
                  AND snapshot_date <= ?
                ORDER BY
                    snapshot_date DESC,
                    is_proxy ASC,
                    CASE data_quality
                        WHEN 'exact' THEN 0
                        WHEN 'approximate' THEN 1
                        WHEN 'proxy' THEN 2
                        WHEN 'partial' THEN 3
                        ELSE 4
                    END,
                    source
                LIMIT 1
                """,
                [index_id, as_of.date()],
            ).fetchone()
            if snapshot is None:
                continue
            snapshot_dates.append(snapshot[0])
            rows = self.conn.execute(
                """
                SELECT
                    constituent_symbol, constituent_name, exchange_code,
                    country_code, currency, sector, industry, weight_pct,
                    market_cap, is_proxy
                FROM benchmark_index_constituent
                WHERE UPPER(index_id) = ?
                  AND snapshot_date = ?
                  AND source = ?
                ORDER BY weight_pct DESC NULLS LAST, constituent_symbol
                LIMIT ?
                """,
                [index_id, snapshot[0], snapshot[1], limit_per_index],
            ).fetchall()
            if rows:
                covered_indexes += 1
            for row in rows:
                is_proxy = bool(snapshot[2] or row[9])
                evidence = candidate_source_evidence(
                    source_domain="benchmark-composition",
                    source_schema_version=BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
                    source_record_id=(
                        f"benchmark:{index_id}:{snapshot[0].isoformat()}:"
                        f"{snapshot[1]}:{row[0]}"
                    ),
                    as_of=_as_utc(snapshot[0]),
                    payload={
                        "index_id": index_id,
                        "snapshot_date": snapshot[0],
                        "source": snapshot[1],
                        "data_quality": snapshot[3],
                        "constituent_symbol": row[0],
                        "constituent_name": row[1],
                        "exchange_code": row[2],
                        "country_code": row[3],
                        "currency": row[4],
                        "sector": row[5],
                        "industry": row[6],
                        "weight_pct": row[7],
                        "market_cap": row[8],
                        "is_proxy": is_proxy,
                    },
                )
                nominations.append(
                    CandidateNomination(
                        source_asset_id=str(row[0]).upper(),
                        ticker=str(row[0]).upper(),
                        source_match=CandidateSourceMatch(
                            source_family="benchmark",
                            source_methodology_version=BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
                            reason_code=(
                                "source.benchmark.proxy_constituent"
                                if is_proxy
                                else "source.benchmark.constituent"
                            ),
                            evidence_refs=(evidence,),
                        ),
                    )
                )
        watermark_as_of = _as_utc(max(snapshot_dates)) if snapshot_dates else None
        coverage = (
            "available"
            if covered_indexes == len(index_ids)
            else "partial"
            if covered_indexes
            else "missing"
        )
        limitations = []
        if covered_indexes < len(index_ids):
            limitations.append("source.benchmark.composition_missing")
        if snapshot_dates and not nominations:
            limitations.append("source.benchmark.constituents_missing")
        return SourceAdapterResult(
            source_family="benchmark",
            watermark=CandidateSourceWatermark(
                source_domain="benchmark-composition",
                source_schema_version=BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state=coverage,
            ),
            nominations=tuple(
                sorted(
                    nominations,
                    key=lambda item: (
                        item.source_asset_id,
                        item.source_match.evidence_refs[0].source_record_id,
                    ),
                )
            ),
            limitations=tuple(limitations),
        )

    def _all_universe_rows(
        self,
        *,
        term: str,
        as_of: datetime,
        limit: int,
    ) -> list[tuple[Any, ...]]:
        like = f"%{term}%"
        as_of_db = _as_db_timestamp(as_of)
        return self.conn.execute(
            """
            WITH source_rows AS (
                SELECT
                    asset_id, COALESCE(symbol, asset_id) AS symbol,
                    COALESCE(asset_type, 'stock') AS asset_type, ccy, name,
                    sector, industry, country, updated_at,
                    'asset' AS source_table, 0 AS source_priority
                FROM asset
                WHERE updated_at <= ?
                  AND COALESCE(asset_type, 'stock') = 'stock'
                  AND (
                      LOWER(asset_id) LIKE ? OR LOWER(COALESCE(symbol, '')) LIKE ? OR
                      LOWER(COALESCE(name, '')) LIKE ? OR LOWER(COALESCE(sector, '')) LIKE ? OR
                      LOWER(COALESCE(industry, '')) LIKE ?
                  )
                UNION ALL
                SELECT
                    asset_id, symbol, asset_type, ccy, name, sector, industry,
                    country, updated_at, 'stock_catalog', 1
                FROM stock_catalog
                WHERE updated_at <= ?
                  AND asset_type = 'stock'
                  AND (
                      LOWER(asset_id) LIKE ? OR LOWER(symbol) LIKE ? OR
                      LOWER(name) LIKE ? OR LOWER(COALESCE(sector, '')) LIKE ? OR
                      LOWER(COALESCE(industry, '')) LIKE ?
                  )
            ),
            deduplicated AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY asset_id ORDER BY source_priority
                ) AS source_rank
                FROM source_rows
            )
            SELECT
                asset_id, symbol, asset_type, ccy, name, sector, industry,
                country, updated_at, source_table
            FROM deduplicated
            WHERE source_rank = 1
            ORDER BY
                CASE
                    WHEN LOWER(asset_id) = ? THEN 0
                    WHEN LOWER(symbol) = ? THEN 1
                    ELSE 2
                END,
                asset_id
            LIMIT ?
            """,
            [
                as_of_db,
                like,
                like,
                like,
                like,
                like,
                as_of_db,
                like,
                like,
                like,
                like,
                like,
                term,
                term,
                limit,
            ],
        ).fetchall()


def candidate_source_evidence(
    *,
    source_domain: str,
    source_schema_version: str,
    source_record_id: str,
    as_of: datetime,
    payload: dict[str, Any],
) -> CandidateEvidenceRef:
    payload_hash = canonical_hash(payload)
    values = {
        "source_domain": source_domain,
        "source_schema_version": source_schema_version,
        "source_record_id": source_record_id,
        "as_of": as_of,
        "payload_hash": payload_hash,
    }
    return CandidateEvidenceRef(
        evidence_id=candidate_evidence_id(**values),
        freshness_state="unknown",
        **values,
    )


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc).replace(microsecond=0)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _as_db_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("source adapter as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _validate_limit(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")

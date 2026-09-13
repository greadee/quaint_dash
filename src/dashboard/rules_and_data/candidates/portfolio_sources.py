"""Point-in-time portfolio-gap and association candidate sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from math import isfinite
from typing import Any

from dashboard.rules_and_data.candidates.models import (
    CandidateEvidenceRef,
    CandidateSourceMatch,
    CandidateSourceWatermark,
)
from dashboard.rules_and_data.candidates.source_adapters import (
    CandidateNomination,
    CandidateNominationBlock,
    SourceAdapterResult,
    candidate_source_evidence,
)
from dashboard.rules_and_data.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    InvestorProfile,
)

PORTFOLIO_GAP_POLICY_VERSION = "candidate-portfolio-gap.v1"
PORTFOLIO_ANALYTICS_SCHEMA_VERSION = "portfolio-analytics-snapshot.v1"
BENCHMARK_EXPOSURE_SCHEMA_VERSION = "benchmark-exposure-snapshot.v1"
BUSINESS_PEER_SCHEMA_VERSION = "business-strength-peer-group.v1"
BUSINESS_CLASSIFICATION_SCHEMA_VERSION = "asset-business-classification.v1"
PROFILE_THEME_SCHEMA_VERSION = "profile-theme-benchmark.v1"

MIN_PORTFOLIO_CLASSIFIED_WEIGHT = 0.75
MIN_PORTFOLIO_TOTAL_WEIGHT = 0.95
MAX_PORTFOLIO_TOTAL_WEIGHT = 1.05
MIN_BENCHMARK_TOTAL_WEIGHT = 0.95
MAX_BENCHMARK_TOTAL_WEIGHT = 1.05
MIN_BENCHMARK_CLASSIFIED_WEIGHT = 0.75
MIN_SECTOR_CONCENTRATION = 0.40
MIN_GEOGRAPHY_CONCENTRATION = 0.60
MIN_TARGET_WEIGHT = 0.05
MIN_GAP_WEIGHT = 0.10
MAX_THEME_EXISTING_WEIGHT = 0.30

_UNKNOWN_CLASSIFICATIONS = frozenset(
    {"", "broad market", "other", "unclassified", "unknown"}
)
_THEME_INDEX_BY_PROFILE_KEY = {
    "ai": "THEME_AI",
    "artificial intelligence": "THEME_AI",
    "battery technology": "THEME_BATTERY_TECH",
    "clean energy": "THEME_CLEAN_ENERGY",
    "cloud": "THEME_CLOUD",
    "cloud computing": "THEME_CLOUD",
    "cybersecurity": "THEME_CYBERSECURITY",
    "fintech": "THEME_FINTECH",
    "infrastructure": "THEME_INFRASTRUCTURE",
    "robotics": "THEME_ROBOTICS",
    "robotics and automation": "THEME_ROBOTICS",
    "solar": "THEME_SOLAR",
    "uranium": "THEME_URANIUM_NUCLEAR",
    "uranium and nuclear": "THEME_URANIUM_NUCLEAR",
}


@dataclass(frozen=True)
class _ExposureSnapshot:
    snapshot_date: date
    effective_as_of: datetime
    values: dict[str, float]
    source: str
    source_type: str
    is_proxy: bool


@dataclass(frozen=True)
class _Gap:
    key: str
    label: str
    portfolio_weight: float
    benchmark_weight: float

    @property
    def gap_weight(self) -> float:
        return self.benchmark_weight - self.portfolio_weight


@dataclass(frozen=True)
class _ClassifiedAsset:
    asset_id: str
    ticker: str
    label: str
    source: str
    effective_as_of: datetime
    payload: dict[str, Any]


class CandidatePortfolioSourceAdapters:
    """Nominate research candidates from stored gaps and associations."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def sector_gaps(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        benchmark_index_id: str | None,
        investor_profile: InvestorProfile | None,
        limit_per_gap: int = 25,
    ) -> SourceAdapterResult:
        return self._dimension_gaps(
            source_family="sector_gap",
            dimension="sector",
            portfolio_id=portfolio_id,
            as_of=as_of,
            benchmark_index_id=benchmark_index_id,
            investor_profile=investor_profile,
            concentration_threshold=MIN_SECTOR_CONCENTRATION,
            limit_per_gap=limit_per_gap,
        )

    def geography_gaps(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        benchmark_index_id: str | None,
        investor_profile: InvestorProfile | None,
        limit_per_gap: int = 25,
    ) -> SourceAdapterResult:
        return self._dimension_gaps(
            source_family="geography_gap",
            dimension="country",
            portfolio_id=portfolio_id,
            as_of=as_of,
            benchmark_index_id=benchmark_index_id,
            investor_profile=investor_profile,
            concentration_threshold=MIN_GEOGRAPHY_CONCENTRATION,
            limit_per_gap=limit_per_gap,
        )

    def peer_associations(
        self,
        *,
        as_of: datetime,
        seed_asset_ids: tuple[str, ...],
        limit_per_group: int = 25,
    ) -> SourceAdapterResult:
        normalized_as_of = _normalize_as_of(as_of)
        _validate_limit("peer association limit", limit_per_group)
        seeds = tuple(sorted({value.upper().strip() for value in seed_asset_ids if value.strip()}))
        if not seeds:
            return _unsupported(
                source_family="peer",
                source_domain="business-strength-peer-groups",
                schema_version=BUSINESS_PEER_SCHEMA_VERSION,
                limitation="source.peer.seed_not_supplied",
            )

        placeholders = ", ".join("?" for _ in seeds)
        as_of_db = _as_db_timestamp(normalized_as_of)
        rows = self.conn.execute(
            f"""
            WITH seed_groups AS (
                SELECT DISTINCT
                    member.peer_group_id,
                    member.asset_id AS seed_asset_id,
                    member.effective_from AS seed_effective_from,
                    member.effective_to AS seed_effective_to
                FROM business_strength_peer_member member
                WHERE UPPER(member.asset_id) IN ({placeholders})
                  AND member.effective_from <= ?
                  AND (member.effective_to IS NULL OR member.effective_to >= ?)
            ),
            active_targets AS (
                SELECT
                    member.peer_group_id,
                    member.asset_id,
                    member.effective_from,
                    member.effective_to,
                    ROW_NUMBER() OVER (
                        PARTITION BY member.peer_group_id, member.asset_id
                        ORDER BY member.effective_from DESC
                    ) AS active_rank
                FROM business_strength_peer_member member
                WHERE member.effective_from <= ?
                  AND (member.effective_to IS NULL OR member.effective_to >= ?)
            )
            SELECT
                target.asset_id,
                COALESCE(asset.symbol, target.asset_id) AS ticker,
                seed.seed_asset_id,
                groups.id,
                groups.name,
                groups.template_code,
                groups.definition_json,
                groups.updated_at,
                target.effective_from,
                target.effective_to,
                seed.seed_effective_from,
                seed.seed_effective_to
            FROM seed_groups seed
            JOIN business_strength_peer_group groups
              ON groups.id = seed.peer_group_id
             AND groups.updated_at <= ?
            JOIN active_targets target
              ON target.peer_group_id = groups.id
             AND target.active_rank = 1
            LEFT JOIN asset
              ON asset.asset_id = target.asset_id
             AND asset.updated_at <= ?
            WHERE UPPER(target.asset_id) NOT IN ({placeholders})
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY groups.id
                ORDER BY target.asset_id, seed.seed_asset_id
            ) <= ?
            ORDER BY target.asset_id, groups.id, seed.seed_asset_id
            """,
            [
                *seeds,
                normalized_as_of.date(),
                normalized_as_of.date(),
                normalized_as_of.date(),
                normalized_as_of.date(),
                as_of_db,
                as_of_db,
                *seeds,
                limit_per_group,
            ],
        ).fetchall()
        relevant = self.conn.execute(
            f"""
            SELECT MAX(groups.updated_at), COUNT(DISTINCT groups.id)
            FROM business_strength_peer_member member
            JOIN business_strength_peer_group groups ON groups.id = member.peer_group_id
            WHERE UPPER(member.asset_id) IN ({placeholders})
              AND member.effective_from <= ?
              AND (member.effective_to IS NULL OR member.effective_to >= ?)
              AND groups.updated_at <= ?
            """,
            [
                *seeds,
                normalized_as_of.date(),
                normalized_as_of.date(),
                as_of_db,
            ],
        ).fetchone()
        watermark_as_of = _as_utc(relevant[0]) if relevant and relevant[0] else None
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=_source_match(
                    source_family="peer",
                    methodology_version=BUSINESS_PEER_SCHEMA_VERSION,
                    reason_code="source.peer.group_member",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="business-strength-peer-groups",
                            source_schema_version=BUSINESS_PEER_SCHEMA_VERSION,
                            source_record_id=f"peer-group:{row[3]}:{row[0]}:{row[2]}",
                            as_of=_as_utc(row[7]),
                            payload={
                                "candidate_asset_id": row[0],
                                "seed_asset_id": row[2],
                                "peer_group_id": row[3],
                                "name": row[4],
                                "template_code": row[5],
                                "definition_json": row[6],
                                "target_effective_from": row[8],
                                "target_effective_to": row[9],
                                "seed_effective_from": row[10],
                                "seed_effective_to": row[11],
                            },
                        ),
                    ),
                ),
            )
            for row in rows
        )
        return SourceAdapterResult(
            source_family="peer",
            watermark=CandidateSourceWatermark(
                source_domain="business-strength-peer-groups",
                source_schema_version=BUSINESS_PEER_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state="partial" if watermark_as_of else "missing",
            ),
            nominations=nominations,
            limitations=(
                ("source.peer.group_definition_current_state_only",)
                if watermark_as_of
                else ("source.peer.mapping_missing",)
            ),
        )

    def industry_associations(
        self,
        *,
        as_of: datetime,
        seed_asset_ids: tuple[str, ...],
        limit_per_industry: int = 25,
    ) -> SourceAdapterResult:
        normalized_as_of = _normalize_as_of(as_of)
        _validate_limit("industry association limit", limit_per_industry)
        seeds = tuple(sorted({value.upper().strip() for value in seed_asset_ids if value.strip()}))
        if not seeds:
            return _unsupported(
                source_family="industry",
                source_domain="asset-business-classification",
                schema_version=BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
                limitation="source.industry.seed_not_supplied",
            )

        placeholders = ", ".join("?" for _ in seeds)
        as_of_db = _as_db_timestamp(normalized_as_of)
        rows = self.conn.execute(
            f"""
            WITH active_classification AS (
                SELECT
                    classification.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY classification.asset_id
                        ORDER BY classification.effective_from DESC
                    ) AS active_rank
                FROM asset_business_classification classification
                WHERE classification.effective_from <= ?
                  AND (
                      classification.effective_to IS NULL
                      OR classification.effective_to >= ?
                  )
                  AND classification.updated_at <= ?
            ),
            seed_industries AS (
                SELECT asset_id AS seed_asset_id, industry
                FROM active_classification
                WHERE active_rank = 1
                  AND UPPER(asset_id) IN ({placeholders})
                  AND industry IS NOT NULL
            )
            SELECT
                target.asset_id,
                COALESCE(asset.symbol, target.asset_id) AS ticker,
                seed.seed_asset_id,
                target.industry,
                target.sector,
                target.template_code,
                target.classification_source,
                target.confidence,
                target.effective_from,
                target.effective_to,
                target.updated_at
            FROM seed_industries seed
            JOIN active_classification target
              ON LOWER(target.industry) = LOWER(seed.industry)
             AND target.active_rank = 1
            LEFT JOIN asset
              ON asset.asset_id = target.asset_id
             AND asset.updated_at <= ?
            WHERE UPPER(target.asset_id) NOT IN ({placeholders})
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY LOWER(target.industry)
                ORDER BY target.confidence DESC, target.asset_id, seed.seed_asset_id
            ) <= ?
            ORDER BY target.asset_id, target.industry, seed.seed_asset_id
            """,
            [
                normalized_as_of.date(),
                normalized_as_of.date(),
                as_of_db,
                *seeds,
                as_of_db,
                *seeds,
                limit_per_industry,
            ],
        ).fetchall()
        relevant = self.conn.execute(
            f"""
            SELECT MAX(updated_at), COUNT(*)
            FROM asset_business_classification
            WHERE UPPER(asset_id) IN ({placeholders})
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to >= ?)
              AND updated_at <= ?
              AND industry IS NOT NULL
            """,
            [
                *seeds,
                normalized_as_of.date(),
                normalized_as_of.date(),
                as_of_db,
            ],
        ).fetchone()
        watermark_as_of = _as_utc(relevant[0]) if relevant and relevant[0] else None
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=_source_match(
                    source_family="industry",
                    methodology_version=BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
                    reason_code="source.industry.association",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="asset-business-classification",
                            source_schema_version=BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
                            source_record_id=(
                                f"industry:{_taxonomy_key(row[3])}:{row[0]}:{row[2]}"
                            ),
                            as_of=_as_utc(row[10]),
                            payload={
                                "candidate_asset_id": row[0],
                                "seed_asset_id": row[2],
                                "industry": row[3],
                                "sector": row[4],
                                "template_code": row[5],
                                "classification_source": row[6],
                                "confidence": row[7],
                                "effective_from": row[8],
                                "effective_to": row[9],
                            },
                        ),
                    ),
                ),
            )
            for row in rows
        )
        return SourceAdapterResult(
            source_family="industry",
            watermark=CandidateSourceWatermark(
                source_domain="asset-business-classification",
                source_schema_version=BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state="partial" if watermark_as_of else "missing",
            ),
            nominations=nominations,
            limitations=(
                ("source.industry.classification_current_state_only",)
                if watermark_as_of
                else ("source.industry.classification_missing",)
            ),
        )

    def profile_themes(
        self,
        *,
        as_of: datetime,
        investor_profile: InvestorProfile | None,
        portfolio_id: int | None = None,
        limit_per_theme: int = 25,
    ) -> SourceAdapterResult:
        normalized_as_of = _normalize_as_of(as_of)
        _validate_limit("profile theme limit", limit_per_theme)
        if investor_profile is None:
            return _unsupported(
                source_family="theme",
                source_domain="profile-theme-benchmark",
                schema_version=PROFILE_THEME_SCHEMA_VERSION,
                limitation="source.theme.profile_not_supplied",
            )

        profile_evidence = candidate_profile_evidence(investor_profile, "theme")
        conflict = candidate_profile_conflict(
            investor_profile,
            normalized_as_of,
            "theme",
            expected_portfolio_id=portfolio_id,
        )
        eligible_tilts = tuple(
            tilt
            for tilt in investor_profile.theme_tilts
            if 0 < tilt.weight < MAX_THEME_EXISTING_WEIGHT
        )
        if not eligible_tilts:
            return SourceAdapterResult(
                source_family="theme",
                watermark=CandidateSourceWatermark(
                    source_domain="profile-theme-benchmark",
                    source_schema_version=PROFILE_THEME_SCHEMA_VERSION,
                    as_of=_as_utc(investor_profile.as_of),
                    coverage_state="available",
                ),
                nominations=(),
                limitations=("source.theme.no_underrepresented_profile_theme",),
            )

        nominations: list[CandidateNomination] = []
        blocks: list[CandidateNominationBlock] = []
        snapshot_dates: list[date] = []
        missing_mappings = 0
        missing_compositions = 0
        used_proxy = False
        for tilt in sorted(eligible_tilts, key=lambda item: (_taxonomy_key(item.key), item.key)):
            index_id = _THEME_INDEX_BY_PROFILE_KEY.get(_taxonomy_key(tilt.key))
            if index_id is None:
                missing_mappings += 1
                continue
            snapshot, rows = self._theme_rows(
                index_id=index_id,
                as_of=normalized_as_of,
                limit=limit_per_theme,
            )
            if snapshot is None or not rows:
                missing_compositions += 1
                continue
            snapshot_dates.append(snapshot[0])
            used_proxy = used_proxy or bool(snapshot[2])
            for row in rows:
                evidence = candidate_source_evidence(
                    source_domain="profile-theme-benchmark",
                    source_schema_version=PROFILE_THEME_SCHEMA_VERSION,
                    source_record_id=(
                        f"theme:{_taxonomy_key(tilt.key)}:{index_id}:"
                        f"{snapshot[0].isoformat()}:{row[0]}"
                    ),
                    as_of=_as_utc(snapshot[0]),
                    payload={
                        "profile_id": investor_profile.profile_id,
                        "profile_theme": tilt.key,
                        "profile_theme_weight": tilt.weight,
                        "profile_theme_confidence": tilt.confidence,
                        "index_id": index_id,
                        "index_name": snapshot[4],
                        "source": snapshot[1],
                        "is_proxy": bool(snapshot[2] or row[2]),
                        "constituent_symbol": row[0],
                        "constituent_name": row[1],
                        "weight_pct": row[3],
                        "policy_max_existing_weight": MAX_THEME_EXISTING_WEIGHT,
                    },
                )
                match = _source_match(
                    source_family="theme",
                    methodology_version=PROFILE_THEME_SCHEMA_VERSION,
                    reason_code="source.theme.profile_consistent",
                    evidence_refs=(profile_evidence, evidence),
                )
                if conflict:
                    blocks.append(
                        CandidateNominationBlock(
                            source_asset_id=str(row[0]).upper(),
                            ticker=str(row[0]).upper(),
                            reason_code=conflict,
                            source_match=match,
                        )
                    )
                else:
                    nominations.append(
                        CandidateNomination(
                            source_asset_id=str(row[0]).upper(),
                            ticker=str(row[0]).upper(),
                            source_match=match,
                        )
                    )

        watermark_as_of = (
            _as_utc(max(snapshot_dates))
            if snapshot_dates
            else _as_utc(investor_profile.as_of)
        )
        limitations = []
        if missing_mappings:
            limitations.append("source.theme.mapping_missing")
        if missing_compositions:
            limitations.append("source.theme.composition_missing")
        if used_proxy:
            limitations.append("source.theme.proxy_composition")
        if conflict:
            limitations.append(conflict)
        coverage = (
            "partial"
            if limitations
            else "available"
        )
        return SourceAdapterResult(
            source_family="theme",
            watermark=CandidateSourceWatermark(
                source_domain="profile-theme-benchmark",
                source_schema_version=PROFILE_THEME_SCHEMA_VERSION,
                as_of=watermark_as_of,
                coverage_state=coverage,
            ),
            nominations=tuple(_sort_nominations(nominations)),
            blocked_nominations=tuple(_sort_blocks(blocks)),
            limitations=tuple(sorted(limitations)),
        )

    def _dimension_gaps(
        self,
        *,
        source_family: str,
        dimension: str,
        portfolio_id: int,
        as_of: datetime,
        benchmark_index_id: str | None,
        investor_profile: InvestorProfile | None,
        concentration_threshold: float,
        limit_per_gap: int,
    ) -> SourceAdapterResult:
        normalized_as_of = _normalize_as_of(as_of)
        _validate_limit(f"{source_family} limit", limit_per_gap)
        domain = f"portfolio-{source_family.replace('_', '-')}"
        if not benchmark_index_id:
            return _unsupported(
                source_family=source_family,
                source_domain=domain,
                schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                limitation=f"source.{source_family}.benchmark_not_supplied",
            )
        if investor_profile is None:
            return _unsupported(
                source_family=source_family,
                source_domain=domain,
                schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                limitation=f"source.{source_family}.profile_not_supplied",
            )

        portfolio = self._portfolio_exposure(
            portfolio_id=portfolio_id,
            as_of=normalized_as_of,
            dimension=dimension,
        )
        benchmark = self._benchmark_exposure(
            index_id=benchmark_index_id,
            as_of=normalized_as_of,
            dimension=dimension,
        )
        if portfolio is None or benchmark is None:
            watermark_dates = tuple(
                item.effective_as_of
                for item in (portfolio, benchmark)
                if item is not None
            )
            return SourceAdapterResult(
                source_family=source_family,
                watermark=CandidateSourceWatermark(
                    source_domain=domain,
                    source_schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                    as_of=max(watermark_dates, default=None),
                    coverage_state="missing",
                ),
                nominations=(),
                limitations=(
                    f"source.{source_family}.portfolio_snapshot_missing"
                    if portfolio is None
                    else f"source.{source_family}.benchmark_snapshot_missing",
                ),
            )

        profile_evidence = candidate_profile_evidence(investor_profile, dimension)
        conflict = candidate_profile_conflict(
            investor_profile,
            normalized_as_of,
            dimension,
            expected_portfolio_id=portfolio_id,
        )
        gaps, coverage_limitations = _calculate_gaps(
            portfolio=portfolio,
            benchmark=benchmark,
            concentration_threshold=concentration_threshold,
        )
        if not gaps:
            limitations = list(coverage_limitations)
            if not limitations:
                limitations.append(f"source.{source_family}.no_material_gap")
            return SourceAdapterResult(
                source_family=source_family,
                watermark=CandidateSourceWatermark(
                    source_domain=domain,
                    source_schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                    as_of=max(portfolio.effective_as_of, benchmark.effective_as_of),
                    coverage_state="partial" if coverage_limitations else "available",
                ),
                nominations=(),
                limitations=tuple(sorted(limitations)),
            )

        nominations: list[CandidateNomination] = []
        blocks: list[CandidateNominationBlock] = []
        for gap in gaps:
            gap_evidence = candidate_source_evidence(
                source_domain=domain,
                source_schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                source_record_id=(
                    f"gap:{portfolio_id}:{benchmark_index_id.upper()}:"
                    f"{dimension}:{gap.key}:{portfolio.snapshot_date.isoformat()}:"
                    f"{benchmark.snapshot_date.isoformat()}"
                ),
                as_of=max(portfolio.effective_as_of, benchmark.effective_as_of),
                payload={
                    "portfolio_id": portfolio_id,
                    "benchmark_index_id": benchmark_index_id.upper(),
                    "dimension": dimension,
                    "dimension_value": gap.label,
                    "portfolio_weight": gap.portfolio_weight,
                    "benchmark_weight": gap.benchmark_weight,
                    "gap_weight": gap.gap_weight,
                    "portfolio_snapshot_date": portfolio.snapshot_date,
                    "benchmark_snapshot_date": benchmark.snapshot_date,
                    "benchmark_source": benchmark.source,
                    "benchmark_source_type": benchmark.source_type,
                    "benchmark_is_proxy": benchmark.is_proxy,
                    "policy": {
                        "minimum_gap_weight": MIN_GAP_WEIGHT,
                        "minimum_target_weight": MIN_TARGET_WEIGHT,
                        "concentration_threshold": concentration_threshold,
                    },
                },
            )
            for candidate in self._classified_assets(
                dimension=dimension,
                taxonomy_key=gap.key,
                as_of=normalized_as_of,
                limit=limit_per_gap,
            ):
                classification_evidence = candidate_source_evidence(
                    source_domain="candidate-asset-classification",
                    source_schema_version=BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
                    source_record_id=(
                        f"classification:{dimension}:{candidate.asset_id}:"
                        f"{candidate.effective_as_of.isoformat()}"
                    ),
                    as_of=candidate.effective_as_of,
                    payload=candidate.payload,
                )
                match = _source_match(
                    source_family=source_family,
                    methodology_version=PORTFOLIO_GAP_POLICY_VERSION,
                    reason_code=f"source.{source_family}.underweight",
                    evidence_refs=(
                        gap_evidence,
                        classification_evidence,
                        profile_evidence,
                    ),
                )
                if conflict:
                    blocks.append(
                        CandidateNominationBlock(
                            source_asset_id=candidate.asset_id,
                            ticker=candidate.ticker,
                            reason_code=conflict,
                            source_match=match,
                        )
                    )
                else:
                    nominations.append(
                        CandidateNomination(
                            source_asset_id=candidate.asset_id,
                            ticker=candidate.ticker,
                            source_match=match,
                        )
                    )

        limitations = list(coverage_limitations)
        limitations.append(f"source.{source_family}.asset_classification_current_state_only")
        if benchmark.is_proxy:
            limitations.append(f"source.{source_family}.benchmark_proxy")
        if conflict:
            limitations.append(conflict)
        return SourceAdapterResult(
            source_family=source_family,
            watermark=CandidateSourceWatermark(
                source_domain=domain,
                source_schema_version=PORTFOLIO_GAP_POLICY_VERSION,
                as_of=max(portfolio.effective_as_of, benchmark.effective_as_of),
                coverage_state="partial",
            ),
            nominations=tuple(_sort_nominations(nominations)),
            blocked_nominations=tuple(_sort_blocks(blocks)),
            limitations=tuple(sorted(set(limitations))),
        )

    def _portfolio_exposure(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        dimension: str,
    ) -> _ExposureSnapshot | None:
        row = self.conn.execute(
            """
            SELECT snapshot_date, payload_json, refreshed_at
            FROM portfolio_analytics_snapshot
            WHERE portfolio_id = ?
              AND snapshot_date <= ?
              AND refreshed_at <= ?
            ORDER BY snapshot_date DESC, refreshed_at DESC
            LIMIT 1
            """,
            [portfolio_id, as_of.date(), _as_db_timestamp(as_of)],
        ).fetchone()
        if row is None:
            return None
        payload = _json_object(row[1])
        decomposition = _json_object(payload.get("risk_decomposition"))
        values = _exposure_values(decomposition.get(f"{dimension}_exposure"))
        if not values:
            return None
        return _ExposureSnapshot(
            snapshot_date=row[0],
            effective_as_of=_as_utc(row[0]),
            values=values,
            source="portfolio_analytics_snapshot",
            source_type=PORTFOLIO_ANALYTICS_SCHEMA_VERSION,
            is_proxy=False,
        )

    def _benchmark_exposure(
        self,
        *,
        index_id: str,
        as_of: datetime,
        dimension: str,
    ) -> _ExposureSnapshot | None:
        selected = self.conn.execute(
            """
            SELECT snapshot_date, source, source_type, is_proxy, SUM(weight_pct)
            FROM benchmark_index_exposure_snapshot
            WHERE UPPER(index_id) = UPPER(?)
              AND dimension_type = ?
              AND snapshot_date <= ?
              AND fetched_at <= ?
            GROUP BY snapshot_date, source, source_type, is_proxy
            ORDER BY
                snapshot_date DESC,
                is_proxy ASC,
                CASE source_type
                    WHEN 'computed_from_constituents' THEN 0
                    WHEN 'factsheet' THEN 1
                    WHEN 'etf_proxy' THEN 2
                    ELSE 3
                END,
                source
            LIMIT 1
            """,
            [index_id, dimension, as_of.date(), _as_db_timestamp(as_of)],
        ).fetchone()
        if selected is None:
            return None
        rows = self.conn.execute(
            """
            SELECT dimension_value, weight_pct
            FROM benchmark_index_exposure_snapshot
            WHERE UPPER(index_id) = UPPER(?)
              AND snapshot_date = ?
              AND dimension_type = ?
              AND source = ?
            ORDER BY dimension_value
            """,
            [index_id, selected[0], dimension, selected[1]],
        ).fetchall()
        values = _exposure_values({str(row[0]): row[1] for row in rows})
        if not values:
            return None
        return _ExposureSnapshot(
            snapshot_date=selected[0],
            effective_as_of=_as_utc(selected[0]),
            values=values,
            source=str(selected[1]),
            source_type=str(selected[2]),
            is_proxy=bool(selected[3]),
        )

    def _classified_assets(
        self,
        *,
        dimension: str,
        taxonomy_key: str,
        as_of: datetime,
        limit: int,
    ) -> tuple[_ClassifiedAsset, ...]:
        as_of_db = _as_db_timestamp(as_of)
        if dimension == "sector":
            rows = self.conn.execute(
                """
                WITH active_classification AS (
                    SELECT
                        classification.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY classification.asset_id
                            ORDER BY classification.effective_from DESC
                        ) AS active_rank
                    FROM asset_business_classification classification
                    WHERE classification.effective_from <= ?
                      AND (
                          classification.effective_to IS NULL
                          OR classification.effective_to >= ?
                      )
                      AND classification.updated_at <= ?
                )
                SELECT
                    asset.asset_id,
                    COALESCE(asset.symbol, asset.asset_id),
                    COALESCE(classification.sector, asset.sector) AS label,
                    classification.template_code,
                    classification.classification_source,
                    classification.confidence,
                    classification.effective_from,
                    classification.effective_to,
                    COALESCE(classification.updated_at, asset.updated_at),
                    CASE
                        WHEN classification.asset_id IS NULL THEN 'asset'
                        ELSE 'asset_business_classification'
                    END AS source
                FROM asset
                LEFT JOIN active_classification classification
                  ON classification.asset_id = asset.asset_id
                 AND classification.active_rank = 1
                WHERE asset.updated_at <= ?
                  AND COALESCE(asset.asset_type, 'stock') = 'stock'
                ORDER BY asset.asset_id
                """,
                [as_of.date(), as_of.date(), as_of_db, as_of_db],
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT
                    asset_id,
                    COALESCE(symbol, asset_id),
                    country,
                    NULL,
                    'asset',
                    NULL,
                    NULL,
                    NULL,
                    updated_at,
                    'asset'
                FROM asset
                WHERE updated_at <= ?
                  AND COALESCE(asset_type, 'stock') = 'stock'
                ORDER BY asset_id
                """,
                [as_of_db],
            ).fetchall()
        candidates = []
        for row in rows:
            label = str(row[2] or "").strip()
            if _taxonomy_key(label) != taxonomy_key:
                continue
            effective_as_of = _as_utc(row[8])
            candidates.append(
                _ClassifiedAsset(
                    asset_id=str(row[0]),
                    ticker=str(row[1]).upper(),
                    label=label,
                    source=str(row[9]),
                    effective_as_of=effective_as_of,
                    payload={
                        "asset_id": row[0],
                        "ticker": str(row[1]).upper(),
                        "dimension": dimension,
                        "classification": label,
                        "template_code": row[3],
                        "classification_source": row[4],
                        "confidence": row[5],
                        "effective_from": row[6],
                        "effective_to": row[7],
                        "source_table": row[9],
                    },
                )
            )
            if len(candidates) >= limit:
                break
        return tuple(candidates)

    def _theme_rows(
        self,
        *,
        index_id: str,
        as_of: datetime,
        limit: int,
    ) -> tuple[tuple[Any, ...] | None, list[tuple[Any, ...]]]:
        snapshot = self.conn.execute(
            """
            SELECT
                composition.snapshot_date,
                composition.source,
                composition.is_proxy,
                composition.data_quality,
                benchmark.index_name
            FROM benchmark_index_composition_snapshot composition
            JOIN benchmark_index benchmark ON benchmark.index_id = composition.index_id
            WHERE composition.index_id = ?
              AND benchmark.index_category = 'theme'
              AND benchmark.updated_at <= ?
              AND composition.snapshot_date <= ?
              AND composition.fetched_at <= ?
            ORDER BY
                composition.snapshot_date DESC,
                composition.is_proxy ASC,
                composition.source
            LIMIT 1
            """,
            [
                index_id,
                _as_db_timestamp(as_of),
                as_of.date(),
                _as_db_timestamp(as_of),
            ],
        ).fetchone()
        if snapshot is None:
            return None, []
        rows = self.conn.execute(
            """
            SELECT constituent_symbol, constituent_name, is_proxy, weight_pct
            FROM benchmark_index_constituent
            WHERE index_id = ?
              AND snapshot_date = ?
              AND source = ?
            ORDER BY weight_pct DESC NULLS LAST, constituent_symbol
            LIMIT ?
            """,
            [index_id, snapshot[0], snapshot[1], limit],
        ).fetchall()
        return tuple(snapshot), rows


def _calculate_gaps(
    *,
    portfolio: _ExposureSnapshot,
    benchmark: _ExposureSnapshot,
    concentration_threshold: float,
) -> tuple[tuple[_Gap, ...], tuple[str, ...]]:
    portfolio_known = _known_exposure(portfolio.values)
    benchmark_known = _known_exposure(benchmark.values)
    portfolio_total = sum(portfolio.values.values())
    portfolio_coverage = sum(portfolio_known.values())
    benchmark_total = sum(benchmark.values.values())
    benchmark_coverage = sum(benchmark_known.values())
    limitations = []
    if not MIN_PORTFOLIO_TOTAL_WEIGHT <= portfolio_total <= MAX_PORTFOLIO_TOTAL_WEIGHT:
        limitations.append("source.gap.portfolio_total_invalid")
    if portfolio_coverage < MIN_PORTFOLIO_CLASSIFIED_WEIGHT:
        limitations.append("source.gap.portfolio_classification_incomplete")
    if not MIN_BENCHMARK_TOTAL_WEIGHT <= benchmark_total <= MAX_BENCHMARK_TOTAL_WEIGHT:
        limitations.append("source.gap.benchmark_total_invalid")
    if benchmark_coverage < MIN_BENCHMARK_CLASSIFIED_WEIGHT:
        limitations.append("source.gap.benchmark_classification_incomplete")
    if limitations:
        return (), tuple(sorted(limitations))
    if not portfolio_known or max(portfolio_known.values()) < concentration_threshold:
        return (), ()

    labels = {
        _taxonomy_key(label): label
        for label in benchmark.values
        if not _is_unknown(label)
    }
    gaps = tuple(
        sorted(
            (
                _Gap(
                    key=key,
                    label=labels[key],
                    portfolio_weight=portfolio_known.get(key, 0.0),
                    benchmark_weight=target,
                )
                for key, target in benchmark_known.items()
                if target >= MIN_TARGET_WEIGHT
                and target - portfolio_known.get(key, 0.0) >= MIN_GAP_WEIGHT
            ),
            key=lambda item: (-item.gap_weight, item.key),
        )
    )
    return gaps, ()


def candidate_profile_conflict(
    profile: InvestorProfile,
    as_of: datetime,
    dimension: str,
    *,
    expected_portfolio_id: int | None,
) -> str | None:
    if (
        expected_portfolio_id is not None
        and profile.portfolio_id != str(expected_portfolio_id)
    ):
        return "guardrail.profile.portfolio_conflict"
    if profile.as_of > as_of:
        return "guardrail.profile.future_snapshot"
    if profile.schema_version != INVESTOR_PROFILE_SCHEMA_VERSION:
        return "guardrail.profile.schema_conflict"
    if profile.methodology_version != INVESTOR_PROFILE_METHODOLOGY_VERSION:
        return "guardrail.profile.methodology_conflict"
    if "insufficient_data" in profile.archetype_labels or profile.confidence < 0.35:
        return "guardrail.profile.insufficient_data"
    gap_by_dimension = {
        "country": "missing.geography.classification",
        "sector": "missing.sector.classification",
        "theme": "missing.theme.classification",
    }
    if gap_by_dimension[dimension] in profile.data_gaps:
        return f"guardrail.profile.{dimension}_coverage_conflict"
    if dimension == "theme" and not profile.theme_tilts:
        return "guardrail.profile.theme_conflict"
    return None


def candidate_profile_evidence(
    profile: InvestorProfile,
    dimension: str,
) -> CandidateEvidenceRef:
    return candidate_source_evidence(
        source_domain="investor-profile",
        source_schema_version=profile.schema_version,
        source_record_id=f"profile:{profile.profile_id}:{dimension}",
        as_of=_as_utc(profile.as_of),
        payload={
            "profile_id": profile.profile_id,
            "portfolio_id": profile.portfolio_id,
            "methodology_version": profile.methodology_version,
            "input_snapshot_hash": profile.input_snapshot_hash,
            "inference_scope": profile.inference_scope,
            "suitability_status": profile.suitability_status,
            "archetype_labels": profile.archetype_labels,
            "confidence": profile.confidence,
            "factor_scores": tuple(
                _profile_dimension_payload(item) for item in profile.factor_scores
            ),
            "observed_risk_posture": _profile_dimension_payload(
                profile.observed_risk_posture
            ),
            "concentration_profile": _profile_dimension_payload(
                profile.concentration_profile
            ),
            "geography_tilt": _profile_dimension_payload(profile.geography_tilt),
            "sector_tilts": tuple(
                _profile_tilt_payload(item) for item in profile.sector_tilts
            ),
            "theme_tilts": tuple(
                _profile_tilt_payload(item) for item in profile.theme_tilts
            ),
            "allocation_mix": {
                "etf_weight": profile.allocation_mix.etf_weight,
                "passive_weight": profile.allocation_mix.passive_weight,
                "direct_stock_weight": profile.allocation_mix.direct_stock_weight,
                "classified_weight": profile.allocation_mix.classified_weight,
                "label": profile.allocation_mix.label,
                "confidence": profile.allocation_mix.confidence,
                "evidence_ids": tuple(sorted(profile.allocation_mix.evidence_refs)),
            },
            "data_gaps": profile.data_gaps,
            "dimension": dimension,
        },
    )


def _profile_dimension_payload(value: Any) -> dict[str, Any]:
    return {
        "code": value.code,
        "score": value.score,
        "label": value.label,
        "confidence": value.confidence,
        "evidence_ids": tuple(sorted(value.evidence_refs)),
        "data_gaps": tuple(sorted(value.data_gaps)),
    }


def _profile_tilt_payload(value: Any) -> dict[str, Any]:
    return {
        "dimension": value.dimension,
        "key": value.key,
        "weight": value.weight,
        "label": value.label,
        "confidence": value.confidence,
        "evidence_ids": tuple(sorted(value.evidence_refs)),
    }


def _source_match(
    *,
    source_family: str,
    methodology_version: str,
    reason_code: str,
    evidence_refs: tuple[CandidateEvidenceRef, ...],
) -> CandidateSourceMatch:
    return CandidateSourceMatch(
        source_family=source_family,
        source_methodology_version=methodology_version,
        reason_code=reason_code,
        evidence_refs=tuple(
            sorted(
                {ref.evidence_id: ref for ref in evidence_refs}.values(),
                key=lambda item: item.evidence_id,
            )
        ),
    )


def _unsupported(
    *,
    source_family: str,
    source_domain: str,
    schema_version: str,
    limitation: str,
) -> SourceAdapterResult:
    return SourceAdapterResult(
        source_family=source_family,
        watermark=CandidateSourceWatermark(
            source_domain=source_domain,
            source_schema_version=schema_version,
            as_of=None,
            coverage_state="unsupported",
        ),
        nominations=(),
        limitations=(limitation,),
    )


def _exposure_values(value: Any) -> dict[str, float]:
    source = _json_object(value)
    values = {
        str(label).strip(): float(weight)
        for label, weight in source.items()
        if _valid_weight(weight)
    }
    total = sum(values.values())
    if total > 1.5:
        values = {label: weight / 100.0 for label, weight in values.items()}
    return dict(sorted(values.items(), key=lambda item: (_taxonomy_key(item[0]), item[0])))


def _known_exposure(values: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for label, weight in values.items():
        if _is_unknown(label):
            continue
        key = _taxonomy_key(label)
        result[key] = result.get(key, 0.0) + weight
    return result


def _valid_weight(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number >= 0


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _taxonomy_key(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    return " ".join(
        part
        for part in "".join(
            character if character.isalnum() else " "
            for character in text
        ).split()
        if part
    )


def _is_unknown(value: Any) -> bool:
    return _taxonomy_key(value) in _UNKNOWN_CLASSIFICATIONS


def _sort_nominations(
    values: list[CandidateNomination],
) -> list[CandidateNomination]:
    return sorted(
        values,
        key=lambda item: (
            item.source_asset_id,
            item.source_match.reason_code,
            tuple(ref.evidence_id for ref in item.source_match.evidence_refs),
        ),
    )


def _sort_blocks(
    values: list[CandidateNominationBlock],
) -> list[CandidateNominationBlock]:
    return sorted(
        values,
        key=lambda item: (
            item.source_asset_id,
            item.reason_code,
            tuple(ref.evidence_id for ref in item.source_match.evidence_refs),
        ),
    )


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("portfolio source as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _as_db_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc).replace(microsecond=0)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _validate_limit(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")

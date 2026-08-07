"""Deterministic outside-holding candidate pool assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dashboard.ai_brain.candidates.models import (
    CandidateEvidenceRef,
    CandidateSourceMatch,
    CandidateSourceWatermark,
    CandidateWarning,
)
from dashboard.ai_brain.candidates.portfolio_sources import (
    CandidatePortfolioSourceAdapters,
)
from dashboard.ai_brain.candidates.source_adapters import (
    CandidateNomination,
    CandidateSourceAdapters,
    SourceAdapterResult,
)
from dashboard.ai_brain.models import InvestorProfile
from dashboard.assets import cdr_underlying_symbol

IDENTITY_METHODOLOGY_VERSION = "candidate-economic-exposure.v1"


@dataclass(frozen=True)
class ResolvedCandidateIdentity:
    source_asset_id: str
    canonical_asset_id: str | None
    ticker: str
    economic_exposure_id: str
    resolution_state: str
    comparison_keys: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return self.canonical_asset_id is not None and self.resolution_state != "unresolved"


@dataclass(frozen=True)
class CandidatePoolItem:
    asset_id: str
    ticker: str
    economic_exposure_id: str
    source_matches: tuple[CandidateSourceMatch, ...]
    evidence_refs: tuple[CandidateEvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.source_matches or not self.evidence_refs:
            raise ValueError("candidate pool items require source matches and evidence")
        evidence_ids = {ref.evidence_id for ref in self.evidence_refs}
        nested_ids = {
            ref.evidence_id
            for match in self.source_matches
            for ref in match.evidence_refs
        }
        if not nested_ids.issubset(evidence_ids):
            raise ValueError("candidate pool evidence must include every source-match reference")

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted({match.reason_code for match in self.source_matches}))


@dataclass(frozen=True)
class CandidatePoolExclusion:
    asset_id: str
    ticker: str
    economic_exposure_id: str
    reason_code: str
    evidence_refs: tuple[CandidateEvidenceRef, ...]


@dataclass(frozen=True)
class BlockedCandidateIdentity:
    source_asset_id: str
    ticker: str
    reason_code: str
    source_matches: tuple[CandidateSourceMatch, ...]
    warnings: tuple[CandidateWarning, ...]
    evidence_refs: tuple[CandidateEvidenceRef, ...]


@dataclass(frozen=True)
class CandidatePoolResult:
    portfolio_id: int
    as_of: datetime
    methodology_version: str
    source_watermarks: tuple[CandidateSourceWatermark, ...]
    candidates: tuple[CandidatePoolItem, ...]
    exclusions: tuple[CandidatePoolExclusion, ...]
    blocked_identities: tuple[BlockedCandidateIdentity, ...]
    source_limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("candidate pool as_of must be timezone-aware")
        if self.as_of.microsecond:
            raise ValueError("candidate pool as_of must use whole-second precision")


class CandidateAssetIdentityResolver:
    """Resolve repository assets and documented wrapper equivalence without guessing."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def resolve(
        self,
        *,
        asset_id: str,
        ticker: str,
        as_of: datetime,
    ) -> ResolvedCandidateIdentity:
        normalized_as_of = _normalize_as_of(as_of)
        record = self._asset_record(
            asset_id=asset_id,
            ticker=ticker,
            as_of=normalized_as_of,
        )
        if record is None:
            normalized_ticker = ticker.upper().strip()
            return ResolvedCandidateIdentity(
                source_asset_id=asset_id,
                canonical_asset_id=None,
                ticker=normalized_ticker,
                economic_exposure_id=f"unresolved:{normalized_ticker}",
                resolution_state="unresolved",
                comparison_keys=(f"symbol:{normalized_ticker}",),
            )

        underlying_symbol = cdr_underlying_symbol(
            asset_id=record[0],
            symbol=record[1],
            asset_subtype=record[2],
            name=record[3],
            description=record[4],
        )
        if underlying_symbol:
            underlying = self._asset_record(
                asset_id=underlying_symbol,
                ticker=underlying_symbol,
                as_of=normalized_as_of,
            )
            if underlying is None:
                return ResolvedCandidateIdentity(
                    source_asset_id=record[0],
                    canonical_asset_id=None,
                    ticker=record[1],
                    economic_exposure_id=f"unresolved:{underlying_symbol}",
                    resolution_state="unresolved",
                    comparison_keys=(
                        f"asset:{record[0].upper()}",
                        f"symbol:{underlying_symbol}",
                    ),
                )
            canonical_asset_id = underlying[0].upper()
            canonical_ticker = underlying[1].upper()
            return ResolvedCandidateIdentity(
                source_asset_id=record[0],
                canonical_asset_id=canonical_asset_id,
                ticker=canonical_ticker,
                economic_exposure_id=f"asset:{canonical_asset_id}",
                resolution_state="resolved_underlying",
                comparison_keys=(
                    f"asset:{canonical_asset_id}",
                    f"symbol:{canonical_ticker}",
                ),
            )

        canonical_asset_id = record[0].upper()
        canonical_ticker = record[1].upper()
        return ResolvedCandidateIdentity(
            source_asset_id=record[0],
            canonical_asset_id=canonical_asset_id,
            ticker=canonical_ticker,
            economic_exposure_id=f"asset:{canonical_asset_id}",
            resolution_state="direct",
            comparison_keys=(
                f"asset:{canonical_asset_id}",
                f"symbol:{canonical_ticker}",
            ),
        )

    def _asset_record(
        self,
        *,
        asset_id: str,
        ticker: str,
        as_of: datetime,
    ) -> tuple[str, str, str | None, str | None, str | None] | None:
        as_of_db = as_of.astimezone(timezone.utc).replace(tzinfo=None)
        exact = self.conn.execute(
            """
            SELECT asset_id, COALESCE(symbol, asset_id), asset_subtype, name, description
            FROM asset
            WHERE UPPER(asset_id) = UPPER(?)
              AND updated_at <= ?
            LIMIT 1
            """,
            [asset_id, as_of_db],
        ).fetchone()
        if exact is not None:
            return tuple(exact)
        catalog_exact = self.conn.execute(
            """
            SELECT asset_id, symbol, NULL, name, NULL
            FROM stock_catalog
            WHERE UPPER(asset_id) = UPPER(?)
              AND updated_at <= ?
            LIMIT 1
            """,
            [asset_id, as_of_db],
        ).fetchone()
        if catalog_exact is not None:
            return tuple(catalog_exact)

        rows = self.conn.execute(
            """
            SELECT asset_id, symbol, asset_subtype, name, description, 0 AS source_priority
            FROM asset
            WHERE UPPER(COALESCE(symbol, asset_id)) = UPPER(?)
              AND updated_at <= ?
            UNION ALL
            SELECT asset_id, symbol, NULL, name, NULL, 1
            FROM stock_catalog
            WHERE UPPER(symbol) = UPPER(?)
              AND updated_at <= ?
            ORDER BY source_priority, asset_id
            """,
            [ticker, as_of_db, ticker, as_of_db],
        ).fetchall()
        distinct: dict[str, tuple[Any, ...]] = {}
        for row in rows:
            distinct.setdefault(str(row[0]).upper(), row)
        if len(distinct) != 1:
            return None
        row = next(iter(distinct.values()))
        return row[0], row[1], row[2], row[3], row[4]


class OutsideHoldingUniverseBuilder:
    """Merge source nominations and fail closed on held or unresolved exposure identity."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.adapters = CandidateSourceAdapters(conn)
        self.portfolio_sources = CandidatePortfolioSourceAdapters(conn)
        self.identity = CandidateAssetIdentityResolver(conn)

    def build(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        ranking_factor: str = "aggregate",
        ranking_universe: str = "all",
        ranking_limit: int = 25,
        search_terms: tuple[str, ...] = (),
        benchmark_index_ids: tuple[str, ...] = (),
        comparison_benchmark_index_id: str | None = None,
        investor_profile: InvestorProfile | None = None,
    ) -> CandidatePoolResult:
        normalized_as_of = _normalize_as_of(as_of)
        held_asset_ids = self._held_asset_ids(portfolio_id, normalized_as_of)
        source_results = (
            self.adapters.top_ranked(
                as_of=normalized_as_of,
                factor=ranking_factor,
                universe=ranking_universe,
                limit=ranking_limit,
            ),
            self.adapters.active_watchlist(as_of=normalized_as_of),
            self.adapters.all_universe_search(
                as_of=normalized_as_of,
                search_terms=search_terms,
            ),
            self.adapters.benchmark_constituents(
                as_of=normalized_as_of,
                benchmark_index_ids=benchmark_index_ids,
            ),
            self.portfolio_sources.sector_gaps(
                portfolio_id=portfolio_id,
                as_of=normalized_as_of,
                benchmark_index_id=comparison_benchmark_index_id,
                investor_profile=investor_profile,
            ),
            self.portfolio_sources.geography_gaps(
                portfolio_id=portfolio_id,
                as_of=normalized_as_of,
                benchmark_index_id=comparison_benchmark_index_id,
                investor_profile=investor_profile,
            ),
            self.portfolio_sources.peer_associations(
                as_of=normalized_as_of,
                seed_asset_ids=held_asset_ids,
            ),
            self.portfolio_sources.industry_associations(
                as_of=normalized_as_of,
                seed_asset_ids=held_asset_ids,
            ),
            self.portfolio_sources.profile_themes(
                as_of=normalized_as_of,
                investor_profile=investor_profile,
                portfolio_id=portfolio_id,
            ),
        )
        return self.build_from_sources(
            portfolio_id=portfolio_id,
            as_of=normalized_as_of,
            source_results=source_results,
        )

    def build_from_sources(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        source_results: tuple[SourceAdapterResult, ...],
    ) -> CandidatePoolResult:
        normalized_as_of = _normalize_as_of(as_of)
        held_source_ids = set(self._held_asset_ids(portfolio_id, normalized_as_of))
        held_identities = tuple(
            self.identity.resolve(
                asset_id=asset_id,
                ticker=asset_id,
                as_of=normalized_as_of,
            )
            for asset_id in sorted(held_source_ids)
        )
        held_keys = {
            key
            for identity in held_identities
            for key in identity.comparison_keys
        }
        held_canonical_ids = {
            identity.canonical_asset_id
            for identity in held_identities
            if identity.canonical_asset_id is not None
        }

        grouped: dict[str, list[tuple[CandidateNomination, ResolvedCandidateIdentity]]] = {}
        blocked_entries: dict[
            tuple[str, str],
            list[
                tuple[
                    CandidateSourceMatch,
                    ResolvedCandidateIdentity,
                    str,
                    str,
                ]
            ],
        ] = {}
        for result in source_results:
            for nomination in result.nominations:
                identity = self.identity.resolve(
                    asset_id=nomination.source_asset_id,
                    ticker=nomination.ticker,
                    as_of=normalized_as_of,
                )
                if not identity.resolved:
                    blocked_entries.setdefault(
                        (
                            "guardrail.identity.unresolved",
                            identity.economic_exposure_id,
                        ),
                        [],
                    ).append(
                        (
                            nomination.source_match,
                            identity,
                            nomination.source_asset_id,
                            nomination.ticker,
                        )
                    )
                    continue
                grouped.setdefault(identity.economic_exposure_id, []).append(
                    (nomination, identity)
                )
            for blocked_nomination in result.blocked_nominations:
                identity = self.identity.resolve(
                    asset_id=blocked_nomination.source_asset_id,
                    ticker=blocked_nomination.ticker,
                    as_of=normalized_as_of,
                )
                reason_code = (
                    blocked_nomination.reason_code
                    if identity.resolved
                    else "guardrail.identity.unresolved"
                )
                blocked_entries.setdefault(
                    (reason_code, identity.economic_exposure_id),
                    [],
                ).append(
                    (
                        blocked_nomination.source_match,
                        identity,
                        blocked_nomination.source_asset_id,
                        blocked_nomination.ticker,
                    )
                )

        candidates: list[CandidatePoolItem] = []
        exclusions: list[CandidatePoolExclusion] = []
        for exposure_id, entries in sorted(grouped.items()):
            matches = _merge_source_matches(
                tuple(entry[0].source_match for entry in entries)
            )
            evidence_refs = _evidence_refs(matches)
            identity = min(
                (entry[1] for entry in entries),
                key=lambda item: (
                    item.resolution_state != "direct",
                    item.canonical_asset_id or "",
                    item.source_asset_id,
                ),
            )
            candidate_keys = {
                key
                for _nomination, entry_identity in entries
                for key in entry_identity.comparison_keys
            }
            is_held = bool(candidate_keys.intersection(held_keys)) or (
                identity.canonical_asset_id in held_canonical_ids
            )
            if is_held:
                direct = any(
                    nomination.source_asset_id.upper() in held_source_ids
                    for nomination, _entry_identity in entries
                )
                exclusions.append(
                    CandidatePoolExclusion(
                        asset_id=identity.canonical_asset_id or identity.source_asset_id,
                        ticker=identity.ticker,
                        economic_exposure_id=exposure_id,
                        reason_code=(
                            "guardrail.exposure.direct_holding"
                            if direct
                            else "guardrail.exposure.equivalent_holding"
                        ),
                        evidence_refs=evidence_refs,
                    )
                )
                continue
            candidates.append(
                CandidatePoolItem(
                    asset_id=identity.canonical_asset_id or identity.source_asset_id,
                    ticker=identity.ticker,
                    economic_exposure_id=exposure_id,
                    source_matches=matches,
                    evidence_refs=evidence_refs,
                )
            )

        blocked: list[BlockedCandidateIdentity] = []
        for (reason_code, exposure_id), entries in blocked_entries.items():
            matches = _merge_source_matches(
                tuple(entry[0] for entry in entries)
            )
            evidence_refs = _evidence_refs(matches)
            identity = min(
                (entry[1] for entry in entries),
                key=lambda item: (item.source_asset_id, item.ticker),
            )
            candidate_keys = {
                key
                for entry in entries
                for key in entry[1].comparison_keys
            }
            if candidate_keys.intersection(held_keys) or (
                identity.canonical_asset_id in held_canonical_ids
            ):
                direct = any(entry[2].upper() in held_source_ids for entry in entries)
                exclusions.append(
                    CandidatePoolExclusion(
                        asset_id=identity.canonical_asset_id or identity.source_asset_id,
                        ticker=identity.ticker,
                        economic_exposure_id=exposure_id,
                        reason_code=(
                            "guardrail.exposure.direct_holding"
                            if direct
                            else "guardrail.exposure.equivalent_holding"
                        ),
                        evidence_refs=evidence_refs,
                    )
                )
                continue
            blocked.append(
                BlockedCandidateIdentity(
                    source_asset_id=identity.source_asset_id,
                    ticker=identity.ticker,
                    reason_code=reason_code,
                    source_matches=matches,
                    warnings=(
                        CandidateWarning(
                            warning_code=reason_code,
                            severity="critical",
                            blocking=True,
                            evidence_refs=evidence_refs,
                        ),
                    ),
                    evidence_refs=evidence_refs,
                )
            )

        limitations = tuple(
            sorted(
                {
                    limitation
                    for result in source_results
                    for limitation in result.limitations
                }.union(
                    self._portfolio_exposure_limitations(
                        portfolio_id,
                        normalized_as_of,
                    )
                )
            )
        )
        return CandidatePoolResult(
            portfolio_id=portfolio_id,
            as_of=normalized_as_of,
            methodology_version=IDENTITY_METHODOLOGY_VERSION,
            source_watermarks=tuple(
                sorted(
                    (result.watermark for result in source_results),
                    key=lambda item: item.source_domain,
                )
            ),
            candidates=tuple(sorted(candidates, key=lambda item: item.asset_id)),
            exclusions=_merge_exclusions(exclusions),
            blocked_identities=tuple(
                sorted(blocked, key=lambda item: (item.source_asset_id, item.reason_code))
            ),
            source_limitations=limitations,
        )

    def _held_asset_ids(
        self,
        portfolio_id: int,
        as_of: datetime,
    ) -> tuple[str, ...]:
        as_of_db = as_of.astimezone(timezone.utc).replace(tzinfo=None)
        rows = self.conn.execute(
            """
            SELECT asset_id
            FROM (
                SELECT asset_id, SUM(quantity) AS quantity
                FROM (
                    SELECT asset_id, SUM(qty) AS quantity
                    FROM txn
                    WHERE portfolio_id = ?
                      AND asset_id IS NOT NULL
                      AND txn_type IN ('buy', 'sell')
                      AND time_stamp <= ?
                      AND NOT EXISTS (
                          SELECT 1
                          FROM broker_portfolio_position_map mapped
                          WHERE mapped.portfolio_id = txn.portfolio_id
                            AND mapped.updated_at <= ?
                      )
                    GROUP BY asset_id
                    UNION ALL
                    SELECT asset_id, quantity
                    FROM broker_portfolio_position_map
                    WHERE portfolio_id = ?
                      AND updated_at <= ?
                ) combined
                GROUP BY asset_id
            ) held
            WHERE quantity <> 0
            ORDER BY asset_id
            """,
            [portfolio_id, as_of_db, as_of_db, portfolio_id, as_of_db],
        ).fetchall()
        return tuple(str(row[0]).upper() for row in rows)

    def _portfolio_exposure_limitations(
        self,
        portfolio_id: int,
        as_of: datetime,
    ) -> set[str]:
        row = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM broker_portfolio_position_map
            WHERE portfolio_id = ?
              AND updated_at <= ?
            """,
            [portfolio_id, as_of.astimezone(timezone.utc).replace(tzinfo=None)],
        ).fetchone()
        return (
            {"portfolio.exposure.broker_snapshot_current_state_only"}
            if row and int(row[0])
            else set()
        )


def _merge_source_matches(
    matches: tuple[CandidateSourceMatch, ...],
) -> tuple[CandidateSourceMatch, ...]:
    grouped: dict[tuple[str, str, str], list[CandidateEvidenceRef]] = {}
    for match in matches:
        key = (
            match.source_family,
            match.reason_code,
            match.source_methodology_version,
        )
        grouped.setdefault(key, []).extend(match.evidence_refs)
    merged = []
    for key, evidence in sorted(grouped.items()):
        refs = tuple(
            sorted(
                {ref.evidence_id: ref for ref in evidence}.values(),
                key=lambda item: item.evidence_id,
            )
        )
        merged.append(
            CandidateSourceMatch(
                source_family=key[0],
                reason_code=key[1],
                source_methodology_version=key[2],
                evidence_refs=refs,
            )
        )
    return tuple(merged)


def _evidence_refs(
    matches: tuple[CandidateSourceMatch, ...],
) -> tuple[CandidateEvidenceRef, ...]:
    return tuple(
        sorted(
            {
                ref.evidence_id: ref
                for match in matches
                for ref in match.evidence_refs
            }.values(),
            key=lambda item: item.evidence_id,
        )
    )


def _merge_exclusions(
    exclusions: list[CandidatePoolExclusion],
) -> tuple[CandidatePoolExclusion, ...]:
    grouped: dict[
        tuple[str, str, str, str],
        dict[str, CandidateEvidenceRef],
    ] = {}
    for item in exclusions:
        key = (
            item.asset_id,
            item.ticker,
            item.economic_exposure_id,
            item.reason_code,
        )
        grouped.setdefault(key, {}).update(
            {ref.evidence_id: ref for ref in item.evidence_refs}
        )
    return tuple(
        CandidatePoolExclusion(
            asset_id=key[0],
            ticker=key[1],
            economic_exposure_id=key[2],
            reason_code=key[3],
            evidence_refs=tuple(
                sorted(evidence.values(), key=lambda item: item.evidence_id)
            ),
        )
        for key, evidence in sorted(grouped.items())
    )


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("candidate pool as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)

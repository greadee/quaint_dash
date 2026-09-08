"""Evidence-aware presentation adapters for decision surfaces.

These functions copy public response models and attach display metadata only. They do not
recalculate values, mutate persistence, or change write-path payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from dashboard.api.evidence_contract import EvidencePolicyInput, evaluate_evidence
from dashboard.api.models import (
    AssetDetail,
    BenchmarkDailyMetric,
    BenchmarkIndexDetail,
    BenchmarkIndexSummary,
    BenchmarkPricePoint,
    BusinessStrengthCategoryResponse,
    BusinessStrengthCompareResponse,
    BusinessStrengthMetricResponse,
    BusinessStrengthScorecardResponse,
    ComparisonFreshness,
    ComparisonWorkspaceResponse,
    EvidenceDisplayResponse,
    NewsArticleResponse,
    NewsFeedResponse,
    PortfolioFundamentalHolding,
    PortfolioFundamentalsResponse,
    RetailSentimentOverviewItem,
    RetailSentimentOverviewResponse,
    RetailSentimentStatusResponse,
    SignalDetailResponse,
    SignalRow,
    SignalsSummaryResponse,
)

UTC = timezone.utc


def _display(item: EvidencePolicyInput) -> EvidenceDisplayResponse:
    return EvidenceDisplayResponse.model_validate(evaluate_evidence(item).to_public_dict())


def _source_kind(name: str | None, *, proxy: bool = False, inferred: bool = False) -> str:
    lowered = (name or "").lower()
    if proxy:
        return "proxy"
    if lowered.strip() == "test" or any(
        marker in lowered for marker in ("fixture", "example.test", "demo", "mock", "sample")
    ):
        return "fixture"
    if inferred:
        return "inferred"
    return "real" if name else "unknown"


def present_asset_detail(
    asset: AssetDetail,
    *,
    observed_at: object | None,
    source: str | None,
    retrieved_at: object | None,
) -> AssetDetail:
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="price",
            source_kind=_source_kind(source, proxy="proxy" in (source or "").lower()),
            source_name=source,
            source_health="healthy",
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            essential_missing_inputs=() if asset.latest_price is not None else ("latest price",),
        )
    )
    return asset.model_copy(update={"evidence": evidence})


def present_asset_analytics(
    payload: dict[str, object],
    *,
    observed_at: object | None,
    source: str | None,
    retrieved_at: object | None,
    price_observed_at: object | None,
    price_source: str | None,
    price_retrieved_at: object | None,
) -> dict[str, object]:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    ai_context = payload.get("ai_context") if isinstance(payload.get("ai_context"), dict) else {}
    missing = ai_context.get("missing_inputs") if isinstance(ai_context, dict) else []
    essential_missing = tuple(str(item) for item in missing) if isinstance(missing, list) else ()
    fundamental_evidence = _display(
        EvidencePolicyInput(
            evidence_type="financial_statement",
            source_kind=_source_kind(source, inferred=True),
            source_name=(f"asset analytics from {source}" if source else "asset analytics"),
            source_health="healthy",
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            essential_missing_inputs=essential_missing,
        )
    )
    price_evidence = _display(
        EvidencePolicyInput(
            evidence_type="price",
            source_kind=_source_kind(price_source, proxy="proxy" in (price_source or "").lower()),
            source_name=price_source,
            source_health="healthy",
            observed_at=price_observed_at,
            retrieved_at=price_retrieved_at,
        )
    )
    return {
        **payload,
        "report": report,
        "evidence": fundamental_evidence.model_dump(mode="json"),
        "fundamental_evidence": fundamental_evidence.model_dump(mode="json"),
        "price_evidence": price_evidence.model_dump(mode="json"),
    }


def _news_health(status: str) -> str:
    return {
        "healthy": "healthy",
        "degraded": "degraded",
        "failed": "blocked",
        "not_started": "blocked",
    }.get(status, "unknown")


def _public_news_url(value: str | None) -> str | None:
    if not value:
        return None
    host = (urlparse(value).hostname or "").lower()
    return None if host == "example.test" or host.endswith(".example.test") else value


def present_news_feed(feed: NewsFeedResponse) -> NewsFeedResponse:
    health = _news_health(feed.provider_status)
    items = [
        _present_news_article(item, health=health, retrieved_at=feed.generated_at)
        for item in feed.items
    ]
    latest = max((item.published_at for item in items if item.published_at), default=None)
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="news",
            source_kind="real" if items else "unknown",
            source_name="normalized news providers" if items else None,
            source_health=health,
            observed_at=latest or feed.last_successful_sync_at,
            retrieved_at=feed.generated_at,
            missing_inputs=() if items else ("news articles",),
        )
    )
    return feed.model_copy(update={"items": items, "evidence": evidence})


def present_news_article(article: NewsArticleResponse) -> NewsArticleResponse:
    return _present_news_article(article, health="unknown", retrieved_at=datetime.now(UTC))


def _present_news_article(
    article: NewsArticleResponse, *, health: str, retrieved_at: datetime
) -> NewsArticleResponse:
    source = article.provider_name or article.provider_code or article.source_name
    kind = _source_kind(" ".join(filter(None, (source, article.canonical_url))))
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="news",
            source_kind=kind,
            source_name=source or None,
            source_health="blocked" if kind == "fixture" else health,
            observed_at=article.published_at,
            retrieved_at=retrieved_at,
        )
    )
    return article.model_copy(
        update={"canonical_url": _public_news_url(article.canonical_url), "evidence": evidence}
    )


def present_retail_sentiment(
    overview: RetailSentimentOverviewResponse,
    status: RetailSentimentStatusResponse,
) -> RetailSentimentOverviewResponse:
    configured = [provider for provider in status.providers if provider.configured]
    post_count = sum(provider.post_count for provider in configured)
    latest = max(
        (provider.latest_post_at for provider in configured if provider.latest_post_at),
        default=None,
    )
    missing = []
    if not configured:
        missing.append("configured Reddit or X provider")
    if post_count == 0:
        missing.append("ingested social posts")
    health = "blocked" if missing else "degraded" if status.failed_jobs else "healthy"
    overall = _display(
        EvidencePolicyInput(
            evidence_type="retail_sentiment",
            source_kind="real" if configured else "unknown",
            source_name="Reddit and X providers" if configured else None,
            source_health=health,
            observed_at=latest,
            retrieved_at=overview.generated_at,
            essential_missing_inputs=tuple(missing),
        )
    )

    def adapt(item: RetailSentimentOverviewItem) -> RetailSentimentOverviewItem:
        evidence = _display(
            EvidencePolicyInput(
                evidence_type="retail_sentiment",
                source_kind="real" if configured else "unknown",
                source_name="Reddit and X providers" if configured else None,
                source_health=health,
                observed_at=item.snapshot_date,
                retrieved_at=overview.generated_at,
                essential_missing_inputs=tuple(missing),
                confidence=item.confidence,
            )
        )
        return item.model_copy(update={"evidence": evidence})

    return overview.model_copy(
        update={
            "holdings": [adapt(item) for item in overview.holdings],
            "popular": [adapt(item) for item in overview.popular],
            "evidence": overall,
        }
    )


def present_portfolio_fundamentals(
    result: PortfolioFundamentalsResponse,
    *,
    source_dates: dict[str, object],
) -> PortfolioFundamentalsResponse:
    def adapt(item: PortfolioFundamentalHolding) -> PortfolioFundamentalHolding:
        source_asset_id = item.valuation_asset_id or item.asset_id
        evidence = _display(
            EvidencePolicyInput(
                evidence_type="financial_statement",
                source_kind="inferred",
                source_name="portfolio fundamentals from financial_statement",
                source_health="healthy",
                observed_at=source_dates.get(source_asset_id),
                retrieved_at=result.as_of,
                essential_missing_inputs=tuple(item.missing_inputs),
            )
        )
        return item.model_copy(update={"evidence": evidence})

    essential = list(result.missing_inputs)
    if result.weighted_expected_cagr.value is None:
        essential.append("weighted expected CAGR")
    observed_dates = [value for value in source_dates.values() if value is not None]
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="financial_statement",
            source_kind="inferred",
            source_name="portfolio fundamentals from financial_statement",
            source_health="healthy",
            observed_at=min(observed_dates) if observed_dates else None,
            retrieved_at=result.as_of,
            essential_missing_inputs=tuple(dict.fromkeys(essential)),
        )
    )
    return result.model_copy(
        update={
            "holdings": [adapt(item) for item in result.holdings],
            "evidence": evidence,
        }
    )


def _present_signal(item: SignalRow) -> SignalRow:
    missing = (
        ()
        if item.missing_data_status == "complete"
        else (item.missing_data_status.replace("_", " "),)
    )
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="monthly_signal",
            source_kind="inferred",
            source_name=item.source or "signal engine",
            source_health="healthy",
            observed_at=item.data_as_of,
            retrieved_at=item.last_evaluated_at,
            missing_inputs=missing,
            confidence=item.confidence,
            effectiveness_sample_size=item.historical_efficacy.sample_size,
        )
    )
    return item.model_copy(update={"evidence": evidence})


def present_signals_summary(summary: SignalsSummaryResponse) -> SignalsSummaryResponse:
    items = [_present_signal(item) for item in summary.items]
    by_id = {item.signal_id: item for item in items}

    def actionable(item: SignalRow) -> bool:
        return item.evidence is not None and item.evidence.action_eligibility != "blocked"

    needs = [by_id.get(item.signal_id, _present_signal(item)) for item in summary.needs_attention]
    opportunities = [
        by_id.get(item.signal_id, _present_signal(item)) for item in summary.top_opportunities
    ]
    metrics = [
        item.model_copy(update={"label": "Older (31d+) or incomplete"})
        if item.label.lower() == "stale or incomplete"
        else item
        for item in summary.metrics
    ]
    return summary.model_copy(
        update={
            "items": sorted(items, key=lambda item: item.evidence.action_eligibility == "blocked"),
            "needs_attention": [item for item in needs if actionable(item)],
            "top_opportunities": [item for item in opportunities if actionable(item)],
            "metrics": metrics,
        }
    )


def present_signal_detail(detail: SignalDetailResponse) -> SignalDetailResponse:
    return detail.model_copy(update={"evidence": _present_signal(detail).evidence})


def present_business_strength(
    scorecard: BusinessStrengthScorecardResponse,
) -> BusinessStrengthScorecardResponse:
    scorecard = BusinessStrengthScorecardResponse.model_validate(scorecard, from_attributes=True)

    def metric(item: BusinessStrengthMetricResponse) -> BusinessStrengthMetricResponse:
        missing = (
            (item.label,)
            if item.value_status not in {"available", "estimated"} or item.raw_value is None
            else ()
        )
        confidence = item.confidence / 100 if item.confidence > 1 else item.confidence
        return item.model_copy(
            update={
                "evidence": _display(
                    EvidencePolicyInput(
                        evidence_type="financial_statement",
                        source_kind=_source_kind(item.source, inferred=True),
                        source_name=item.source or None,
                        source_health="healthy",
                        observed_at=item.source_timestamp,
                        missing_inputs=missing,
                        confidence=confidence,
                    )
                )
            }
        )

    def category(item: BusinessStrengthCategoryResponse) -> BusinessStrengthCategoryResponse:
        metrics = [metric(value) for value in item.metrics]
        missing = tuple(value.label for value in item.metrics if value.raw_value is None)
        return item.model_copy(
            update={
                "metrics": metrics,
                "evidence": _display(
                    EvidencePolicyInput(
                        evidence_type="financial_statement",
                        source_kind="inferred",
                        source_name="Business Strength analyzer",
                        source_health="healthy",
                        observed_at=scorecard.source_data_as_of or scorecard.analysis_date,
                        missing_inputs=missing,
                        confidence=item.confidence_score / 100,
                    )
                ),
            }
        )

    categories = [category(item) for item in scorecard.category_scores]
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="financial_statement",
            source_kind="inferred",
            source_name="Business Strength analyzer",
            source_health="blocked"
            if scorecard.status in {"unavailable", "insufficient_data"}
            else "healthy",
            observed_at=scorecard.source_data_as_of or scorecard.analysis_date,
            missing_inputs=tuple(scorecard.stale_metrics),
            essential_missing_inputs=tuple(scorecard.missing_critical_metrics),
            confidence=scorecard.confidence_score / 100,
        )
    )
    return scorecard.model_copy(update={"category_scores": categories, "evidence": evidence})


def present_business_strength_compare(
    result: BusinessStrengthCompareResponse,
) -> BusinessStrengthCompareResponse:
    result = BusinessStrengthCompareResponse.model_validate(result, from_attributes=True)
    return result.model_copy(
        update={"assets": [present_business_strength(item) for item in result.assets]}
    )


def _comparison_evidence(freshness: ComparisonFreshness) -> ComparisonFreshness:
    price_kind = _source_kind(
        freshness.latest_price_source,
        proxy="proxy" in (freshness.latest_price_source or "").lower(),
    )
    price = _display(
        EvidencePolicyInput(
            evidence_type="price",
            source_kind=price_kind,
            source_name=freshness.latest_price_source,
            source_health="healthy",
            observed_at=freshness.latest_price_date,
            retrieved_at=freshness.latest_price_ingested_at,
        )
    )
    fundamental = _display(
        EvidencePolicyInput(
            evidence_type="financial_statement",
            source_kind=_source_kind(freshness.latest_fundamental_source),
            source_name=freshness.latest_fundamental_source,
            source_health="healthy",
            observed_at=freshness.latest_fiscal_period,
            retrieved_at=freshness.latest_fundamental_ingested_at,
        )
    )
    return freshness.model_copy(
        update={"price_evidence": price, "fundamental_evidence": fundamental}
    )


def present_comparison_workspace(
    result: ComparisonWorkspaceResponse,
    *,
    benchmark_requested: bool,
) -> ComparisonWorkspaceResponse:
    freshness = {symbol: _comparison_evidence(item) for symbol, item in result.freshness.items()}
    series = []
    for item in result.historical_series:
        facts = freshness.get(item.symbol)
        evidence = facts.price_evidence if facts else None
        series.append(item.model_copy(update={"evidence": evidence}))
    assets = [
        item.model_copy(
            update={
                "evidence": freshness.get(item.symbol).price_evidence
                if freshness.get(item.symbol)
                else None
            }
        )
        for item in result.assets
    ]
    reason = None
    if result.benchmark:
        reason = (
            "User-selected benchmark."
            if benchmark_requested
            else "Default benchmark selected from the primary asset association."
        )
    return result.model_copy(
        update={
            "assets": assets,
            "historical_series": series,
            "freshness": freshness,
            "single_asset_mode": len(result.assets) == 1,
            "benchmark_selection_reason": reason,
        }
    )


def _benchmark_kind(detail: BenchmarkIndexDetail | None) -> tuple[str, str | None]:
    symbols = detail.symbols if detail else []
    selected = next((item for item in symbols if item.is_primary), symbols[0] if symbols else None)
    return (
        _source_kind(
            selected.provider if selected else None, proxy=bool(selected and selected.is_proxy)
        ),
        selected.provider if selected else None,
    )


def present_benchmark_summary(
    item: BenchmarkIndexSummary, detail: BenchmarkIndexDetail | None = None
) -> BenchmarkIndexSummary:
    kind, source = _benchmark_kind(detail)
    evidence = _display(
        EvidencePolicyInput(
            evidence_type="benchmark",
            source_kind=kind,
            source_name=source,
            source_health="blocked"
            if item.last_error and not item.daily_price_last_success_at
            else "healthy",
            observed_at=item.latest_metric_date,
            retrieved_at=item.daily_price_last_success_at,
        )
    )
    return item.model_copy(update={"evidence": evidence})


def present_benchmark_detail(item: BenchmarkIndexDetail) -> BenchmarkIndexDetail:
    return item.model_copy(update={"evidence": present_benchmark_summary(item, item).evidence})


def present_benchmark_prices(items: list[BenchmarkPricePoint]) -> list[BenchmarkPricePoint]:
    return [
        item.model_copy(
            update={
                "evidence": _display(
                    EvidencePolicyInput(
                        evidence_type="benchmark",
                        source_kind=_source_kind(item.source, proxy=item.is_proxy),
                        source_name=item.source,
                        source_health="healthy",
                        observed_at=item.date,
                    )
                )
            }
        )
        for item in items
    ]


def present_benchmark_metrics(
    items: list[BenchmarkDailyMetric], detail: BenchmarkIndexDetail
) -> list[BenchmarkDailyMetric]:
    kind, source = _benchmark_kind(detail)
    return [
        item.model_copy(
            update={
                "evidence": _display(
                    EvidencePolicyInput(
                        evidence_type="benchmark",
                        source_kind=kind,
                        source_name=source,
                        source_health="healthy",
                        observed_at=item.metric_date,
                    )
                )
            }
        )
        for item in items
    ]

from datetime import datetime, timezone

import pytest

from dashboard.application.operations import build_operations_health_summary


OBSERVED_AT = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)


def queue(**overrides):
    result = {
        "observed_at": OBSERVED_AT,
        "pending_count": 0,
        "running_count": 0,
        "dead_letter_count": 0,
        "failed_count": 0,
        "oldest_backlog_at": None,
        "oldest_backlog_age_seconds": None,
        "dead_letter_groups": [],
        "failed_groups": [],
        "affected_data_products": [],
    }
    result.update(overrides)
    return result


def worker(**overrides):
    result = {
        "worker_name": "ingestion_background",
        "label": "Routine ingestion",
        "state": "idle",
        "enabled": True,
        "running": True,
        "affected_data_products": ["Prices and market history"],
        "current_failures": {},
    }
    result.update(overrides)
    return result


def summary(**overrides):
    inputs = {"queue": queue(), "workers": [worker()]}
    inputs.update(overrides)
    return build_operations_health_summary(**inputs)


def test_clear_read_only_inputs_are_healthy():
    result = summary()

    assert result["status"] == "healthy"
    assert result["incident_count"] == 0
    assert result["headline"] == "Data health is clear"


@pytest.mark.parametrize(
    ("inputs", "incident_code"),
    [
        (
            {
                "queue": queue(
                    dead_letter_count=1,
                    dead_letter_groups=[
                        {
                            "provider": "fmp",
                            "error_category": "provider_rate_limit",
                            "count": 1,
                            "safe_message": "Provider request limit reached.",
                            "guidance": "Check provider limits before choosing a bounded retry.",
                        }
                    ],
                    affected_data_products=["Earnings and financial statements"],
                ),
            },
            "dead-letters",
        ),
        (
            {
                "queue": queue(
                    pending_count=12,
                    oldest_backlog_age_seconds=7200,
                    affected_data_products=["Prices and market history"],
                ),
                "workers": [worker(enabled=False, state="disabled")],
            },
            "blocked-backlog",
        ),
        (
            {
                "workers": [
                    worker(
                        state="blocked",
                        current_failures={
                            "run": {
                                "safe_message": "The local database could not be accessed.",
                                "guidance": "Check that one app process owns the database.",
                            }
                        },
                    )
                ],
            },
            "worker-ingestion_background",
        ),
        (
            {
                "news_providers": [
                    {
                        "provider_code": "fmp",
                        "provider_name": "Financial Modeling Prep",
                        "is_enabled": True,
                        "status": "failed",
                    }
                ],
            },
            "news-fmp",
        ),
    ],
)
def test_critical_conditions_cannot_report_healthy(inputs, incident_code):
    result = summary(**inputs)

    assert result["status"] == "critical"
    assert incident_code in {incident["code"] for incident in result["incidents"]}


def test_stale_essential_evidence_degrades_health_and_names_domain():
    result = summary(
        benchmark_evidence=[
            {
                "freshness_state": "stale",
                "action_eligibility": "blocked",
                "observed_at": "2026-06-18T00:00:00Z",
            }
        ]
    )

    assert result["status"] == "degraded"
    assert result["affected_data_products"] == ["Benchmarks", "Comparison context"]
    assert result["incidents"][0]["code"] == "stale-benchmarks"


def test_primary_health_link_preserves_incident_and_job_filter():
    result = summary(
        queue=queue(
            pending_count=3,
            oldest_backlog_age_seconds=7200,
            affected_data_products=["Prices and market history"],
        ),
        workers=[worker(enabled=False, state="disabled")],
    )

    assert (
        result["operations_url"]
        == "/operations?incident=blocked-backlog&status=pending#operations-health"
    )


def test_intentionally_disabled_worker_without_backlog_is_informational():
    result = summary(workers=[worker(enabled=False, state="disabled")])

    assert result["status"] == "healthy"
    assert result["incident_count"] == 0
    assert result["informational_count"] == 1
    assert result["incidents"][0]["code"] == "workers-disabled"


def test_enabled_worker_without_background_task_is_critical():
    result = summary(workers=[worker(running=False)])

    assert result["status"] == "critical"
    assert result["incidents"][0]["code"] == "worker-ingestion_background-not-running"
    assert "no active background task" in result["incidents"][0]["detail"]


def test_missing_social_credentials_are_specific_and_non_mutating():
    result = summary(
        retail_providers=[
            {"provider": "reddit", "configured": False},
            {"provider": "x", "configured": False},
        ]
    )
    incident = next(item for item in result["incidents"] if item["code"] == "social-credentials")

    assert result["status"] == "degraded"
    assert "Reddit and X" in incident["detail"]
    assert incident["operations_url"].startswith("/operations?")

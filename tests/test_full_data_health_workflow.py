from tools.run_full_data_health_workflow import scan_payload


def test_health_scan_ignores_methodology_assumptions_and_non_actionable_warnings():
    findings = []

    scan_payload(
        "POST /portfolios/1/optimization/preview",
        {
            "assumptions": ["Historical covariance uses stored daily closes."],
            "warnings": ["CDR expected CAGR is net of wrapper fees."],
        },
        findings,
    )

    assert findings == []


def test_health_scan_keeps_failure_like_endpoint_warnings_actionable():
    findings = []

    scan_payload(
        "GET /portfolios/1/fundamentals",
        {"warnings": ["Missing cash-flow input for ABC."]},
        findings,
    )

    assert len(findings) == 1
    assert findings[0].message == "actionable warnings reported"

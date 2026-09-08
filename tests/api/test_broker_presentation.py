import pytest
from pydantic import ValidationError

from dashboard.api.broker_presentation import present_broker_instrument
from dashboard.api.models import BrokerInstrumentDisplay


def test_instrument_presenter_allowlists_nested_provider_identity():
    instrument = present_broker_instrument(
        provider_symbol=(
            "{'SYMBOL': 'AAPL', 'DESCRIPTION': 'Apple Inc.', "
            "'EXCHANGE': {'CODE': 'NASDAQ'}, 'CURRENCY': {'CODE': 'USD'}, "
            "'FIGI': 'secret-figi', 'LOGO_URL': 'https://logo.example/apple.png'}"
        ),
    )

    assert instrument.model_dump() == {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "local_asset_id": None,
        "resolution_status": "unresolved",
        "display_label": "AAPL - Apple Inc.",
    }
    assert "figi" not in instrument.model_dump_json().lower()
    assert "logo" not in instrument.model_dump_json().lower()


def test_instrument_presenter_uses_deterministic_unsupported_fallback():
    instrument = present_broker_instrument(
        provider_symbol="{'FIGI': 'secret-only'}",
        provider_description="https://provider.example/raw-object",
        provider_currency="{'not': 'a currency'}",
    )

    assert instrument.resolution_status == "unsupported"
    assert instrument.display_label == "Unsupported broker instrument"
    assert instrument.symbol is None
    assert instrument.name is None
    assert instrument.currency is None


def test_instrument_response_model_rejects_nested_values():
    with pytest.raises(ValidationError):
        BrokerInstrumentDisplay.model_validate(
            {
                "symbol": {"symbol": "AAPL"},
                "resolution_status": "unresolved",
                "display_label": "AAPL",
            }
        )

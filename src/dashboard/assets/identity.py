"""Deterministic repository asset and economic-exposure identity helpers."""

from __future__ import annotations

CDR_SYMBOL_ALIASES = {
    "CEGS": "CEG",
    "NVON": "NVO",
    "NOWS": "NOW",
    "VISA": "V",
}

KNOWN_CDR_BASE_SYMBOLS = frozenset(
    {
        "AAPL",
        "AMD",
        "AMZN",
        "ANET",
        "ASML",
        "AVGO",
        "BKNG",
        "CEG",
        "GEV",
        "GOOG",
        "ISRG",
        "LLY",
        "META",
        "MSFT",
        "MU",
        "NOW",
        "NVDA",
        "NVO",
        "SPGI",
        "TSLA",
        "UBER",
        "V",
    }
)


def cdr_underlying_symbol(
    *,
    asset_id: str,
    symbol: str,
    asset_subtype: str | None,
    name: str | None,
    description: str | None,
) -> str | None:
    """Return the documented underlying symbol when the asset is resolvably a CDR."""

    text = " ".join(
        str(value or "")
        for value in (asset_id, symbol, asset_subtype, name, description)
    ).lower()
    normalized_symbol = (symbol or asset_id).upper()
    base = normalized_symbol.split(".", maxsplit=1)[0]
    base = CDR_SYMBOL_ALIASES.get(base, base)
    identified_as_cdr = (
        "cdr" in text
        or "depositary receipt" in text
        or "depository receipt" in text
        or (
            normalized_symbol.endswith((".TO", ".NE"))
            and base in KNOWN_CDR_BASE_SYMBOLS
        )
    )
    return base if identified_as_cdr and base else None

"""Deterministic metric normalization helpers."""

from __future__ import annotations


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def percentile(value: float, population: list[float], direction: str) -> float | None:
    clean = sorted(v for v in population if v is not None and isinstance(v, (int, float)))
    if not clean:
        return None
    rank = sum(1 for item in clean if item <= value) / len(clean) * 100
    return clamp(100 - rank if direction == "lower_is_better" else rank)


def absolute_score(value: float, low: float, high: float, direction: str) -> float:
    if high == low:
        return 50.0
    score = (value - low) / (high - low) * 100
    if direction == "lower_is_better":
        score = 100 - score
    if direction == "target_range":
        mid = (low + high) / 2
        span = max((high - low) / 2, 0.000001)
        score = 100 - abs(value - mid) / span * 100
    return clamp(score)


def combined_score(
    value: float,
    *,
    low: float | None,
    high: float | None,
    direction: str,
    peer_values: list[float],
    historical_values: list[float],
    normalization: str,
) -> tuple[float, float | None, float | None]:
    abs_part = absolute_score(value, low if low is not None else value * 0.5, high if high is not None else value * 1.5, direction)
    peer_part = percentile(value, peer_values, direction)
    history_part = percentile(value, historical_values, direction)
    parts: list[float] = []
    if normalization in {"absolute", "peer_and_history"}:
        parts.append(abs_part)
    if normalization in {"peer", "peer_and_history"} and peer_part is not None:
        parts.append(peer_part)
    if normalization in {"history", "peer_and_history"} and history_part is not None:
        parts.append(history_part)
    if normalization == "target_range":
        parts.append(abs_part)
    return (sum(parts) / len(parts) if parts else abs_part, peer_part, history_part)

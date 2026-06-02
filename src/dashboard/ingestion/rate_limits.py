from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Deque, Iterable


class RateLimitExceeded(RuntimeError):
    """Raised when a provider call would exceed a configured call budget."""


@dataclass(frozen=True)
class RateLimitPolicy:
    provider: str
    calls: int = 60
    period_seconds: float = 60.0
    min_interval_seconds: float = 0.0
    max_calls_per_run: int | None = None


class InMemoryRateLimiter:
    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._timestamps: dict[str, Deque[float]] = {}
        self._run_counts: dict[str, int] = {}
        self._lock = Lock()

    def acquire(self, policy: RateLimitPolicy) -> None:
        if policy.calls < 1:
            raise ValueError("rate limit policy calls must be greater than zero")

        while True:
            sleep_for = self._reserve_or_delay(policy)
            if sleep_for <= 0:
                return
            self._sleeper(sleep_for)

    def _reserve_or_delay(self, policy: RateLimitPolicy) -> float:
        with self._lock:
            now = self._clock()
            key = policy.provider
            timestamps = self._timestamps.setdefault(key, deque())
            run_count = self._run_counts.get(key, 0)

            if policy.max_calls_per_run is not None and run_count >= policy.max_calls_per_run:
                raise RateLimitExceeded(
                    f"{policy.provider} call budget exhausted "
                    f"({policy.max_calls_per_run} calls this run)"
                )

            period_start = now - policy.period_seconds
            while timestamps and timestamps[0] <= period_start:
                timestamps.popleft()

            delays: list[float] = []

            if len(timestamps) >= policy.calls:
                delays.append((timestamps[0] + policy.period_seconds) - now)

            if policy.min_interval_seconds > 0 and timestamps:
                delays.append((timestamps[-1] + policy.min_interval_seconds) - now)

            sleep_for = max(delays, default=0.0)
            if sleep_for > 0:
                return sleep_for

            timestamps.append(now)
            self._run_counts[key] = run_count + 1
            return 0.0


_DEFAULT_LIMITER = InMemoryRateLimiter()


def default_rate_limiter() -> InMemoryRateLimiter:
    return _DEFAULT_LIMITER


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def fmp_rate_limit_policy(provider: str = "fmp") -> RateLimitPolicy:
    return RateLimitPolicy(
        provider=provider,
        calls=env_int("FMP_RATE_LIMIT_PER_MINUTE", 45),
        period_seconds=60.0,
        min_interval_seconds=env_float("FMP_MIN_SECONDS_BETWEEN_CALLS", 1.25),
        max_calls_per_run=env_int("FMP_MAX_CALLS_PER_RUN", 250),
    )


def yfinance_rate_limit_policy(provider: str = "yfinance") -> RateLimitPolicy:
    return RateLimitPolicy(
        provider=provider,
        calls=env_int("YFINANCE_RATE_LIMIT_PER_MINUTE", 30),
        period_seconds=60.0,
        min_interval_seconds=env_float("YFINANCE_MIN_SECONDS_BETWEEN_CALLS", 1.5),
        max_calls_per_run=env_int("YFINANCE_MAX_CALLS_PER_RUN", 500),
    )


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for symbol in symbols:
        clean = str(symbol).strip().upper()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)

    return normalized


def enforce_symbol_cap(provider: str, symbols: list[str], max_symbols: int) -> None:
    if max_symbols < 1:
        raise ValueError(f"{provider} max symbols must be greater than zero")

    if len(symbols) > max_symbols:
        raise RateLimitExceeded(
            f"{provider} symbol budget exceeded: {len(symbols)} requested, "
            f"limit is {max_symbols}"
        )

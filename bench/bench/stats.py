"""Summary statistics for latencies and token counts."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    n: int
    p50: float
    p95: float
    mean: float
    min: float
    max: float


def percentile(values: Sequence[float], fraction: float) -> float:
    """Interpolates linearly between the two nearest ranks, like NumPy's default.

    With small samples p95 sits close to the maximum, so a run needs about 20 turns per
    concurrency level before its p95 means much.
    """
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def summarize(values: Iterable[float]) -> Summary | None:
    """None when there are no values."""
    samples = list(values)
    if not samples:
        return None
    return Summary(
        n=len(samples),
        p50=percentile(samples, 0.5),
        p95=percentile(samples, 0.95),
        mean=sum(samples) / len(samples),
        min=min(samples),
        max=max(samples),
    )

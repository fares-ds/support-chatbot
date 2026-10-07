import pytest

from bench.stats import Summary, summarize


def test_percentiles_interpolate_between_samples() -> None:
    summary = summarize([10, 1, 9, 2, 8, 3, 7, 4, 6, 5])

    assert summary is not None
    assert (summary.n, summary.p50, summary.mean, summary.min, summary.max) == (10, 5.5, 5.5, 1, 10)
    assert summary.p95 == pytest.approx(9.55)


def test_a_single_sample_is_every_statistic() -> None:
    assert summarize([2.5]) == Summary(n=1, p50=2.5, p95=2.5, mean=2.5, min=2.5, max=2.5)


def test_no_samples_have_no_summary() -> None:
    assert summarize([]) is None

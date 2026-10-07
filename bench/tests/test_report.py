from typing import Any

from bench.records import TurnRecord
from bench.report import compare_markdown, level_stats, summary_markdown


def record(**steps: float) -> TurnRecord:
    return TurnRecord(
        sample="en-1",
        language="en",
        worker=0,
        started=0.0,
        steps=steps,
        tokens={},
        tokens_per_second=None,
        category="on_topic",
        outcome="answered",
    )


def level(concurrency: int, records: list[TurnRecord], **resources: Any) -> dict[str, Any]:
    return {
        "concurrency": concurrency,
        "duration": 10.0,
        "stats": level_stats(records),
        "resources": {"memory_peak": {}, "total_memory_peak": 0, "cpu_mean": {}, "cpu_peak": {}}
        | resources,
    }


def results(levels: list[dict[str, Any]], name: str = "dev") -> dict[str, Any]:
    return {
        "name": name,
        "label": None,
        "started_at": "2026-10-07T12:00:00+00:00",
        "method_version": 1,
        "prompt_version": 1,
        "host": {"cpus": 4, "memory_bytes": 8 * 2**30, "architecture": "x86_64", "os": "Ubuntu"},
        "models": {"classifier": "c", "answer": "a", "embedding": "e", "reranker": "r"},
        "budgets": {"classify_in": 1200, "classify_out": 120, "answer_in": 4500, "answer_out": 400},
        "idle": {"memory": {}},
        "levels": levels,
    }


def test_the_summary_shows_p50_and_p95_for_each_step() -> None:
    summary = summary_markdown(results([level(1, [record(rerank=0.2), record(rerank=0.4)])]))

    assert "| Rerank | 0.30 | 0.39 |" in summary


def test_the_summary_shows_each_containers_peak_memory_at_each_level() -> None:
    gib = 2**30
    levels = [
        level(1, [record()], memory_peak={"tei-embed": 3 * gib // 2}, total_memory_peak=2 * gib),
        level(2, [record()], memory_peak={"tei-embed": 2 * gib}, total_memory_peak=3 * gib),
    ]

    summary = summary_markdown(results(levels) | {"idle": {"memory": {"tei-embed": 300 * 2**20}}})

    assert "| tei-embed | 300 MiB | 1.50 GiB | 2.00 GiB |" in summary
    assert "| Whole stack | 300 MiB | 2.00 GiB | 3.00 GiB |" in summary


def test_compare_puts_runs_side_by_side() -> None:
    mac = results([level(1, [record(turn_first_visible=2.0)])], name="mac")
    vps = results([level(1, [record(turn_first_visible=9.0)])], name="vps")

    comparison = compare_markdown([mac, vps])

    assert "| First visible token, end to end · p95 · c=1 | 2.00 | 9.00 |" in comparison


def test_the_summary_opens_with_the_host_models_and_budgets() -> None:
    summary = summary_markdown(results([level(1, [record()])]))

    assert "Docker host: 4 CPUs, 8.00 GiB, x86_64, Ubuntu" in summary
    assert "Budgets: classify 1,200 in, 120 out · answer 4,500 in, 400 out" in summary


def test_the_summary_shows_tokens_and_the_answer_speed() -> None:
    records = [
        TurnRecord(**{**vars(record()), "tokens": {"answer_in": 4400}, "tokens_per_second": 20.0}),
        TurnRecord(**{**vars(record()), "tokens": {"answer_in": 4480}, "tokens_per_second": 10.0}),
    ]

    summary = summary_markdown(results([level(1, records)]))

    assert "| Answer in | 4,440 | 4,480 |" in summary  # p50 and max
    assert "| Answer tokens per second | 15.0 | 10.0 |" in summary  # p50 and slowest


def test_the_summary_shows_the_cores_each_container_used() -> None:
    resources = {"cpu_mean": {"ollama": 1.24}, "cpu_peak": {"ollama": 3.96}}

    summary = summary_markdown(results([level(1, [record()], **resources)]))

    assert "| ollama | 1.2 | 4.0 |" in summary


def test_the_summary_counts_each_levels_outcomes() -> None:
    records = [record(), record(), TurnRecord(**{**vars(record()), "outcome": "abstained"})]

    summary = summary_markdown(results([level(2, records)]))

    assert "- Concurrency 2: 3 turns in 10.0 s: 2 answered, 1 abstained, 0 failed" in summary

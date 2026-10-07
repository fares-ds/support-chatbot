"""Results: per-level statistics, the readable summary, and a comparison of runs."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from bench.records import STEPS, TOKENS, TurnRecord
from bench.stats import summarize

_EMPTY = "-"
"""A cell with nothing to show."""


def level_stats(records: Sequence[TurnRecord]) -> dict[str, Any]:
    """Statistics over a level's turns. Failed turns count only as errors."""
    done = [record for record in records if record.outcome != "error"]

    def summary(values: Sequence[float]) -> dict[str, float] | None:
        result = summarize(values)
        return asdict(result) if result else None

    return {
        "turns": len(records),
        "errors": len(records) - len(done),
        "outcomes": dict(Counter(record.outcome for record in records)),
        "categories": dict(Counter(record.category for record in done if record.category)),
        "steps": {
            step: summary([r.steps[step] for r in done if step in r.steps]) for step in STEPS
        },
        "tokens": {
            key: summary([r.tokens[key] for r in done if key in r.tokens]) for key in TOKENS
        },
        "tokens_per_second": summary(
            [r.tokens_per_second for r in done if r.tokens_per_second is not None]
        ),
    }


def summary_markdown(results: Mapping[str, Any]) -> str:
    levels = results["levels"]
    host, models, budgets = results["host"], results["models"], results["budgets"]
    lines = [
        f"# Benchmark: {_run_name(results)}",
        "",
        f"- Docker host: {host['cpus']} CPUs, {_bytes(host['memory_bytes'])}, "
        f"{host['architecture']}, {host['os']}",
        f"- Classifier: {models['classifier']} · Answer: {models['answer']}",
        f"- Embedding: {models['embedding']} · Reranker: {models['reranker']}",
        f"- Budgets: classify {budgets['classify_in']:,} in, {budgets['classify_out']:,} out · "
        f"answer {budgets['answer_in']:,} in, {budgets['answer_out']:,} out",
        f"- Method {results['method_version']}, prompts {results['prompt_version']}",
        *(_outcomes(level) for level in levels),
        "",
        "## Latency, in seconds",
        "",
        "An abstain ends its answer early, so the answer's first token and first visible token",
        "cover answered turns only.",
        "",
    ]
    lines += _table(
        [
            "Step",
            *[f"{name} · c={level['concurrency']}" for level in levels for name in ("p50", "p95")],
        ],
        [
            [
                label,
                *[
                    _cell(level["stats"]["steps"][step], key)
                    for level in levels
                    for key in ("p50", "p95")
                ],
            ]
            for step, label in STEPS.items()
        ],
    )
    lines += ["", "## Tokens", ""]
    lines += _table(
        [
            "",
            *[f"{name} · c={level['concurrency']}" for level in levels for name in ("p50", "max")],
        ],
        [
            *(
                [
                    label,
                    *[
                        _count(level["stats"]["tokens"][key], name)
                        for level in levels
                        for name in ("p50", "max")
                    ],
                ]
                for key, label in TOKENS.items()
            ),
            [
                "Answer tokens per second",
                *[
                    _speed(level["stats"]["tokens_per_second"], name)
                    for level in levels
                    for name in ("p50", "min")
                ],
            ],
        ],
    )
    lines += ["", "## Memory", ""]
    idle = results["idle"]["memory"]
    names = sorted(
        {*idle, *(name for level in levels for name in level["resources"]["memory_peak"])}
    )
    lines += _table(
        ["Container", "Idle", *[f"Peak · c={level['concurrency']}" for level in levels]],
        [
            *(
                [
                    name,
                    _bytes(idle.get(name)),
                    *[_bytes(level["resources"]["memory_peak"].get(name)) for level in levels],
                ]
                for name in names
            ),
            [
                "Whole stack",
                _bytes(sum(idle.values()) if idle else None),
                *[_bytes(level["resources"]["total_memory_peak"]) for level in levels],
            ],
        ],
    )
    lines += ["", "## CPU cores used", ""]
    cpu_names = sorted({name for level in levels for name in level["resources"]["cpu_mean"]})
    lines += _table(
        [
            "Container",
            *[
                f"{name} · c={level['concurrency']}"
                for level in levels
                for name in ("Mean", "Peak")
            ],
        ],
        [
            [
                name,
                *[
                    _cores(level["resources"][key].get(name))
                    for level in levels
                    for key in ("cpu_mean", "cpu_peak")
                ],
            ]
            for name in cpu_names
        ],
    )
    return "\n".join(lines) + "\n"


def _outcomes(level: Mapping[str, Any]) -> str:
    stats = level["stats"]
    counts = stats["outcomes"]
    return (
        f"- Concurrency {level['concurrency']}: {stats['turns']} turns in "
        f"{level['duration']:.1f} s: {counts.get('answered', 0)} answered, "
        f"{counts.get('abstained', 0)} abstained, {stats['errors']} failed"
    )


def compare_markdown(runs: Sequence[Mapping[str, Any]]) -> str:
    """One column per run, one row per statistic and concurrency level."""
    levels = sorted({level["concurrency"] for run in runs for level in run["levels"]})
    by_level = [{level["concurrency"]: level for level in run["levels"]} for run in runs]
    rows = []
    for concurrency in levels:
        found = [run_levels.get(concurrency) for run_levels in by_level]
        for step, label in STEPS.items():
            for key in ("p50", "p95"):
                rows.append(
                    [
                        f"{label} · {key} · c={concurrency}",
                        *[
                            _cell(level["stats"]["steps"][step], key) if level else _EMPTY
                            for level in found
                        ],
                    ]
                )
        rows.append(
            [
                f"Answer tokens per second · p50 · c={concurrency}",
                *[
                    _speed(level["stats"]["tokens_per_second"], "p50") if level else _EMPTY
                    for level in found
                ],
            ]
        )
        rows.append(
            [
                f"Whole stack, peak memory · c={concurrency}",
                *[
                    _bytes(level["resources"]["total_memory_peak"]) if level else _EMPTY
                    for level in found
                ],
            ]
        )
    header = ["", *[_run_name(run) for run in runs]]
    return "\n".join(["# Benchmark comparison", "", *_table(header, rows)]) + "\n"


def _run_name(run: Mapping[str, Any]) -> str:
    label = f" ({run['label']})" if run.get("label") else ""
    return f"{run['name']}{label}, {run['started_at'][:16].replace('T', ' ')}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---", *["---:"] * (len(header) - 1)]) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def _cell(summary: Mapping[str, float] | None, key: str) -> str:
    return _EMPTY if summary is None else f"{summary[key]:.2f}"


def _bytes(value: int | None) -> str:
    if value is None:
        return _EMPTY
    if value >= 2**30:
        return f"{value / 2**30:.2f} GiB"
    return f"{value / 2**20:.0f} MiB"


def _count(summary: Mapping[str, float] | None, key: str) -> str:
    return _EMPTY if summary is None else f"{summary[key]:,.0f}"


def _speed(summary: Mapping[str, float] | None, key: str) -> str:
    return _EMPTY if summary is None else f"{summary[key]:.1f}"


def _cores(value: float | None) -> str:
    return _EMPTY if value is None else f"{value:.1f}"

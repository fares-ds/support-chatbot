"""Results: per-level statistics, the readable summary, and a comparison of runs."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from bench.data import CATEGORIES
from bench.records import STEPS, TOKENS, TurnRecord
from bench.score import (
    ANSWER_GATES,
    FAILED,
    GATES,
    GROUPS,
    RECALL_GATE,
    REPLY_LANGUAGES,
    Gate,
)
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
    stops_after = results.get("stops_after")
    answer = "not run" if stops_after else models["answer"]
    lines = [
        f"# Benchmark: {_run_name(results)}",
        "",
        f"- Docker host: {host['cpus']} CPUs, {_bytes(host['memory_bytes'])}, "
        f"{host['architecture']}, {host['os']}",
        *_dataset(results),
        f"- Classifier: {models['classifier']} · Answer: {answer}",
        f"- Embedding: {models['embedding']} · Reranker: {models['reranker']}",
        f"- Budgets: classify {budgets['classify_in']:,} in, {budgets['classify_out']:,} out · "
        f"answer {budgets['answer_in']:,} in, {budgets['answer_out']:,} out",
        f"- Method {results['method_version']}, prompts {results['prompt_version']}",
        *(_outcomes(level, stops_after) for level in levels),
        *_scores(results.get("scores")),
        *_retrieval(results.get("scores"), budgets),
        *_answers(results.get("scores"), results.get("judgments")),
        "",
        "## Latency, in seconds",
        "",
        *(
            []
            if stops_after
            else [
                "An abstain ends its answer early, so the answer's first token and first visible",
                "token cover answered turns only.",
                "",
            ]
        ),
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
            if any(level["stats"]["steps"][step] for level in levels)
        ],
    )
    token_rows = [
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
            if any(level["stats"]["tokens"][key] for level in levels)
        ),
        *(
            [
                [
                    "Answer tokens per second: p50, slowest",
                    *[
                        _speed(level["stats"]["tokens_per_second"], name)
                        for level in levels
                        for name in ("p50", "min")
                    ],
                ]
            ]
            if any(level["stats"]["tokens_per_second"] for level in levels)
            else []
        ),
    ]
    if token_rows:
        lines += ["", "## Tokens", ""]
        lines += _table(
            [
                "",
                *[
                    f"{name} · c={level['concurrency']}"
                    for level in levels
                    for name in ("p50", "max")
                ],
            ],
            token_rows,
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


def scores_markdown(results: Mapping[str, Any]) -> str:
    """A run's scores alone, as `bench score` prints them."""
    run_scores = results.get("scores")
    lines = [
        f"# Scores: {_run_name(results)}",
        *_scores(run_scores),
        *_retrieval(run_scores, results["budgets"]),
        *_answers(run_scores, results.get("judgments")),
    ]
    return "\n".join(lines) + "\n"


def _outcomes(level: Mapping[str, Any], stops_after: str | None) -> str:
    stats = level["stats"]
    counts = stats["outcomes"]
    done = {
        "classify": f"{counts.get('classified', 0)} classified",
        "rerank": f"{counts.get('retrieved', 0)} retrieved",
    }.get(
        stops_after or "",
        f"{counts.get('answered', 0)} answered, {counts.get('abstained', 0)} abstained",
    )
    return (
        f"- Concurrency {level['concurrency']}: {stats['turns']} turns in "
        f"{level['duration']:.1f} s: {done}, {stats['errors']} failed"
    )


def _retrieval(scores: Mapping[str, Any] | None, budgets: Mapping[str, Any]) -> list[str]:
    """Recall over the reranker's top 5 per group, against its release gate. Classify-only runs
    and results from before #15 have none."""
    retrieval = (scores or {}).get("retrieval")
    if not retrieval or not retrieval["questions"]:
        return []
    columns = [*retrieval["groups"], "all"]
    recall = retrieval["recall"]
    rows = [
        _group_row(RECALL_GATE.label, recall, columns, _verdict(RECALL_GATE, recall)),
        _group_row("Questions with every source in the top 5", retrieval["complete"], columns),
    ]
    if retrieval["in_prompt"]:
        rows.append(_group_row("Sources in the answer prompt", retrieval["in_prompt"], columns))
    return [
        "",
        "## Retrieval",
        "",
        f"{retrieval['questions']} answerable questions. A source is found when one of the "
        "reranker's top 5 chunks holds its section, or a section below it, in any of its copies. "
        f"The answer prompt takes the first of them that fit its {budgets['sources']:,} tokens.",
        "",
        *_table(["", *[_group_name(c) for c in columns], "Release gate"], rows),
    ]


def _answers(scores: Mapping[str, Any] | None, judgments: Mapping[str, Any] | None) -> list[str]:
    """Gate 3's scores per group against its release gates, and the replies' languages. Runs
    that stop early, and results from before #15, have none."""
    answers = (scores or {}).get("answers")
    if not answers or not answers["groups"]:
        return []
    columns = [*answers["groups"], "all"]
    gates = answers["gates"]
    rows = [
        _group_row(gate.label, gates[key], columns, _verdict(gate, gates[key]))
        for key, gate in ANSWER_GATES.items()
        if gates.get(key)
    ]
    rows += [
        _group_row(label, answers[key], columns)
        for key, label in (
            ("partly_correct", "Answerable questions partly answered: some facts, none wrong"),
            ("abstained", "Answerable questions abstained on"),
            ("cites_expected", "Answers citing a source that holds the facts"),
            ("bad_citations", "Answers citing a source the prompt didn't have"),
            ("cites_none", "Answers citing no source by number"),
            ("unjudged", "Answers the judge could not judge"),
            ("right_language", "Replies in the customer's language (ADR-0035)"),
        )
        if answers[key]
    ]
    if answers["judged"] and judgments:
        intro = (
            f"Judged by {judgments['judge']} on {judgments['judged_at'][:10]}: each expected "
            "fact stated, contradicted or missing, and the claims no source supports. An answer "
            "is correct when it states every fact and contradicts none."
        )
    else:
        intro = (
            "Not judged yet: `bench judge` adds correctness, unsupported claims and the replies' "
            "languages. Code checks the rest."
        )
    lines = [
        "",
        "## Answers",
        "",
        intro,
        "",
        *_table(["", *[_group_name(c) for c in columns], "Release gate"], rows),
    ]
    languages = answers["languages"]
    if languages:
        lines += [
            "",
            "The replies' languages, as the judge names them; ar is Modern Standard Arabic:",
            "",
        ]
        lines += _table(
            ["Group", *REPLY_LANGUAGES],
            [
                [_group_name(group), *[_number(found.get(name)) for name in REPLY_LANGUAGES]]
                for group, found in languages.items()
            ],
        )
    return lines


def _group_row(
    label: str, counts: Mapping[str, Sequence[int]], columns: Sequence[str], gate: str = ""
) -> list[str]:
    """A rate per group, then the release gate's verdict, if any."""
    return [label, *[_rate(counts.get(column)) for column in columns], gate]


def _verdict(gate: Gate, counts: Mapping[str, Sequence[int]]) -> str:
    """The gate's threshold, and whether the pooled rate meets it."""
    sign = "≥" if gate.at_least else "≤"
    return f"{sign} {gate.threshold:.0%}: " + ("met" if gate.met(counts["all"]) else "missed")


_CASES = {
    "needs_history": "Right reply: needs the earlier messages",
    "yes_after_offer": "Right reply: a yes after an offer of a person",
    "injection": "Right reply: injections",
}


def _scores(scores: Mapping[str, Any] | None) -> list[str]:
    """Gate 1's scores per group against the release gates, what each category was given, and
    Gate 1's latency per group. Results from before #14 have none."""
    if not scores:
        return []
    classification = scores["classification"]
    columns = [*classification["groups"], "all"]
    gates = classification["gates"]
    rows = [
        _group_row(gate.label, gates[key], columns, _verdict(gate, gates[key]))
        for key, gate in GATES.items()
        if gates[key]
    ]
    rows.append(_group_row("Right reply: every sample run", classification["right"], columns))
    rows += [
        _group_row(label, classification["cases"][case], columns)
        for case, label in _CASES.items()
        if classification["cases"].get(case)
    ]
    lines = [
        "",
        "## Gate 1: classification",
        "",
        f"{classification['turns']} turns scored against the dataset's labels. A template reply, "
        "off_topic or smalltalk, counts as declined; a failed turn counts against every gate.",
        "",
        *_table(["", *[_group_name(c) for c in columns], "Release gate"], rows),
    ]
    if classification["unknown"]:
        unknown = classification["unknown"]
        lines += [
            "",
            f"Left out: {len(unknown)} turns whose samples the dataset no longer has, such as "
            + ", ".join(unknown[:5])
            + ".",
        ]
    given = [*CATEGORIES, FAILED]
    lines += ["", "What each expected category was given, every group:", ""]
    lines += _table(
        ["Expected", *["Failed" if name == FAILED else name for name in given]],
        [
            [expected, *[_number(counts.get(name)) for name in given]]
            for expected in CATEGORIES
            if (counts := classification["confusion"].get(expected))
        ],
    )
    latency = scores["classify_latency"]
    groups = [g for g in columns if any(g in level["groups"] for level in latency)]
    lines += ["", "Gate 1's seconds per group:", ""]
    lines += _table(
        [
            "Group",
            *[f"{name} · c={level['concurrency']}" for level in latency for name in ("p50", "p95")],
        ],
        [
            [
                _group_name(group),
                *[
                    _cell(level["groups"].get(group), name)
                    for level in latency
                    for name in ("p50", "p95")
                ],
            ]
            for group in groups
        ],
    )
    return lines


def _group_name(group: str) -> str:
    return "All" if group == "all" else group


def _rate(count: Sequence[int] | None) -> str:
    if not count or not count[1]:
        return _EMPTY
    hits, total = count
    return f"{hits / total:.1%} ({hits}/{total})"


def _number(value: int | None) -> str:
    return str(value) if value else _EMPTY


def compare_markdown(runs: Sequence[Mapping[str, Any]]) -> str:
    """One column per run, one row per statistic and concurrency level."""
    levels = sorted({level["concurrency"] for run in runs for level in run["levels"]})
    by_level = [{level["concurrency"]: level for level in run["levels"]} for run in runs]
    rows = _gate_rows(runs)
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
    rows = [row for row in rows if any(cell != _EMPTY for cell in row[1:])]
    return "\n".join(["# Benchmark comparison", "", *_table(header, rows)]) + "\n"


def _gate_rows(runs: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Gate 1's rates, recall@5 and Gate 3's rates per group, for runs that have scores."""
    found = [run["scores"]["classification"] if run.get("scores") else None for run in runs]
    present = {group for scores in found if scores for group in scores["groups"]}
    groups = [*(group for group in GROUPS if group in present), "all"]
    rows = []
    for key, gate in GATES.items():
        for group in groups:
            rows.append(
                [
                    f"{gate.label} · {_group_name(group)}",
                    *[
                        _rate(scores["gates"][key].get(group)) if scores else _EMPTY
                        for scores in found
                    ],
                ]
            )
    rows.append(
        [
            "Right reply: every sample run · All",
            *[_rate(scores["right"].get("all")) if scores else _EMPTY for scores in found],
        ]
    )
    answers = [run["scores"].get("answers") if run.get("scores") else None for run in runs]
    present = {group for found in answers if found for group in found["groups"]}
    for key, gate in ANSWER_GATES.items():
        for group in [*(group for group in GROUPS if group in present), "all"]:
            rows.append(
                [
                    f"{gate.label} · {_group_name(group)}",
                    *[
                        _rate(found["gates"].get(key, {}).get(group)) if found else _EMPTY
                        for found in answers
                    ],
                ]
            )
    recalls = [run["scores"].get("retrieval") if run.get("scores") else None for run in runs]
    present = {group for recall in recalls if recall for group in recall["groups"]}
    for group in [*(group for group in GROUPS if group in present), "all"]:
        rows.append(
            [
                f"{RECALL_GATE.label} · {_group_name(group)}",
                *[_rate(recall["recall"].get(group)) if recall else _EMPTY for recall in recalls],
            ]
        )
    return rows


def _dataset(results: Mapping[str, Any]) -> list[str]:
    """Results from before #13 name no dataset."""
    dataset = results.get("dataset")
    if not dataset:
        return []
    which = results.get("sample_set", "all")
    taken = "" if which == "all" else f", of which the {which} ones ran"
    return [
        f"- Dataset: {dataset['name']}, {dataset['samples']} samples{taken}; "
        f"{dataset['chunks']} chunks from {dataset['documents']} documents"
    ]


def _run_name(run: Mapping[str, Any]) -> str:
    """Its name, the samples it took if not all, its label, and when it started."""
    which = run.get("sample_set", "all")
    taken = f" [{which}]" if which != "all" else ""
    label = f" ({run['label']})" if run.get("label") else ""
    return f"{run['name']}{taken}{label}, {run['started_at'][:16].replace('T', ' ')}"


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

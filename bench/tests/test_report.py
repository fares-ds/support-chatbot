from dataclasses import asdict
from typing import Any

from bench.data import ExpectedSource, Sample, Section
from bench.records import TurnRecord
from bench.report import compare_markdown, level_stats, scores_markdown, summary_markdown
from bench.score import scores


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
        "budgets": {
            "classify_in": 1200,
            "classify_out": 120,
            "answer_in": 4500,
            "answer_out": 400,
            "sources": 2500,
        },
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
    assert "| Answer tokens per second: p50, slowest | 15.0 | 10.0 |" in summary


def test_the_summary_shows_the_cores_each_container_used() -> None:
    resources = {"cpu_mean": {"ollama": 1.24}, "cpu_peak": {"ollama": 3.96}}

    summary = summary_markdown(results([level(1, [record()], **resources)]))

    assert "| ollama | 1.2 | 4.0 |" in summary


def test_the_summary_counts_each_levels_outcomes() -> None:
    records = [record(), record(), TurnRecord(**{**vars(record()), "outcome": "abstained"})]

    summary = summary_markdown(results([level(2, records)]))

    assert "- Concurrency 2: 3 turns in 10.0 s: 2 answered, 1 abstained, 0 failed" in summary


def classified(sample: str, category: str | None, seconds: float = 0.2) -> TurnRecord:
    """A turn of a classify-only run."""
    return TurnRecord(
        **{
            **vars(record(classify=seconds, turn=seconds)),
            "sample": sample,
            "category": category,
            "outcome": "classified" if category else "error",
        }
    )


def with_turns(level: dict[str, Any], records: list[TurnRecord]) -> dict[str, Any]:
    return level | {"turns": [asdict(r) for r in records]}


PEOPLE = [
    Sample("en-person-1", "en", "en", "Can I talk to someone?", category="human_request"),
    Sample("en-person-2", "en", "en", "A human, please", category="human_request"),
    Sample("en-poem", "en", "en", "Write me a poem", category="off_topic"),
]


def test_the_summary_scores_gate_1_per_group_against_the_release_gates() -> None:
    records = [
        classified("en-person-1", "human_request"),
        classified("en-person-2", "on_topic"),
        classified("en-poem", "smalltalk"),
    ]
    run = results([with_turns(level(1, records), records)])

    summary = summary_markdown(
        run | {"scores": scores(run["levels"], PEOPLE, stops_after="classify")}
    )

    assert (
        "| Requests for a person detected | 50.0% (1/2) | 50.0% (1/2) | ≥ 98%: missed |" in summary
    )
    assert "| Off-topic messages declined | 100.0% (1/1) | 100.0% (1/1) | ≥ 95%: met |" in summary
    assert "| human_request | 1 | - | 1 | - | - |" in summary  # given on_topic once


def test_a_classify_only_summary_leaves_out_the_steps_no_turn_reached() -> None:
    records = [classified("en-person-1", "human_request", 0.2), classified("en-poem", None)]
    run = results([with_turns(level(1, records), records)]) | {"stops_after": "classify"}

    summary = summary_markdown(
        run | {"scores": scores(run["levels"], PEOPLE, stops_after="classify")}
    )

    assert "- Concurrency 1: 2 turns in 10.0 s: 1 classified, 1 failed" in summary
    assert "Answer: not run" in summary
    assert "| Rerank |" not in summary
    assert "| en | 0.20 | 0.20 |" in summary  # Gate 1's seconds for the group


def test_compare_sets_classifiers_gate_rates_side_by_side() -> None:
    def classifier_run(name: str, given: str) -> dict[str, Any]:
        records = [classified("en-person-1", "human_request"), classified("en-person-2", given)]
        run = results([with_turns(level(1, records), records)], name=name)
        return run | {
            "stops_after": "classify",
            "scores": scores(run["levels"], PEOPLE, stops_after="classify"),
        }

    comparison = compare_markdown(
        [classifier_run("embedding", "on_topic"), classifier_run("model", "human_request")]
    )

    assert "| Requests for a person detected · All | 50.0% (1/2) | 100.0% (2/2) |" in comparison
    assert "Answer: complete" not in comparison  # no run reached it


QUESTIONS = [
    Sample(
        f"en-q{n}",
        "en",
        "en",
        f"Question {n}",
        expect="answer",
        facts=("a fact",),
        sources=(ExpectedSource((Section("plans.md", (heading,)),)),),
    )
    for n, heading in enumerate(("Prices", "Changes"), 1)
]


def answered(sample: str, *sections: str) -> TurnRecord:
    """A full turn whose reranker's top chunks hold `sections`, all of which reached the
    prompt."""
    return TurnRecord(
        **{
            **vars(record(classify=0.2, rerank=0.3, turn=2.0)),
            "sample": sample,
            "retrieved": [
                {"chunk": n, "document": "plans.md", "sections": [[section]]}
                for n, section in enumerate(sections, 1)
            ],
            "sources": [f"Plans > {section}" for section in sections],
            "prompt_chunks": [
                {"chunk": n, "document": "plans.md", "sections": [[section]]}
                for n, section in enumerate(sections, 1)
            ],
            "answer": "It costs 10 DA [1].",
        }
    )


def test_the_summary_scores_recall_at_5_against_its_gate() -> None:
    records = [answered("en-q1", "Prices"), answered("en-q2", "Prices")]
    run = results([with_turns(level(1, records), records)])

    run_scores = scores(run["levels"], QUESTIONS, stops_after=None)

    summary = summary_markdown(run | {"scores": run_scores})

    assert "| Retrieval recall@5 | 50.0% (1/2) | 50.0% (1/2) | ≥ 90%: missed |" in summary
    assert "| Sources in the answer prompt | 50.0% (1/2) | 50.0% (1/2) |  |" in summary
    assert "first of them that fit its 2,500 tokens" in summary
    assert "Not judged yet" in summary
    assert "| Retrieval recall@5 |" in scores_markdown(run | {"scores": run_scores})


def test_compare_sets_runs_recall_side_by_side() -> None:
    def retrieval_run(name: str, second: str) -> dict[str, Any]:
        records = [answered("en-q1", "Prices"), answered("en-q2", second)]
        run = results([with_turns(level(1, records), records)], name=name)
        return run | {"scores": scores(run["levels"], QUESTIONS, stops_after=None)}

    comparison = compare_markdown([retrieval_run("e5", "Prices"), retrieval_run("bge", "Changes")])

    assert "| Retrieval recall@5 · All | 50.0% (1/2) | 100.0% (2/2) |" in comparison


def verdicts(*facts: str) -> dict[str, Any]:
    return {
        "facts": [{"number": n, "verdict": v, "quote": ""} for n, v in enumerate(facts, 1)],
        "unsupported_claims": [],
        "language": "en",
    }


def test_the_summary_scores_judged_answers_against_gate_3s_gates() -> None:
    records = [answered("en-q1", "Prices"), answered("en-q2", "Changes")]
    judgments = {"en-q1": verdicts("stated"), "en-q2": verdicts("missing")}
    run = results([with_turns(level(1, records), records)]) | {
        "judgments": {
            "judge": "ollama_chat/gpt-oss:120b-cloud",
            "judged_at": "2026-10-11T12:00:00+00:00",
            "turns": judgments,
            "failed": {},
        }
    }
    run_scores = scores(run["levels"], QUESTIONS, stops_after=None, judgments=judgments)

    summary = summary_markdown(run | {"scores": run_scores})

    assert "Judged by ollama_chat/gpt-oss:120b-cloud on 2026-10-11" in summary
    assert (
        "| Answer correctness, answerable questions | 50.0% (1/2) | 50.0% (1/2) | ≥ 85%: missed |"
        in summary
    )
    assert "| Answers with unsupported claims | 0.0% (0/2) | 0.0% (0/2) | ≤ 3%: met |" in summary
    assert "| en | 2 | - | - | - | - |" in summary  # the replies' languages
    assert "Answer correctness, answerable questions" in scores_markdown(
        run | {"scores": run_scores}
    )
    comparison = compare_markdown([run | {"scores": run_scores}])
    assert "| Answer correctness, answerable questions · All | 50.0% (1/2) |" in comparison

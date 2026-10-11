"""Scores a run's turns against the dataset's labels and the PRD's release gates: Gate 1's
classification (#14), retrieval recall@5 and the answers (#15).

A count is a pair, [hits, total], so that a reader sees how few samples a rate rests on.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from bench.data import CASES, ExpectedSource, Sample
from bench.stats import summarize

GROUPS = ("en", "fr", "ar", "darija-latin", "darija-arabic")
"""The order results are reported in. "all" pools them."""

TEMPLATE_REPLIES = frozenset({"off_topic", "smalltalk"})
"""Categories that get a template reply and no answer, so a message given either was declined."""

FAILED = "error"
"""What the confusion table calls a turn that failed before Gate 1 decided."""


@dataclass(frozen=True)
class Gate:
    label: str
    threshold: float
    at_least: bool
    """The rate must be at least the threshold, or else at most it."""

    def met(self, count: Sequence[int]) -> bool:
        hits, total = count
        if self.at_least:
            return hits >= self.threshold * total
        return hits <= self.threshold * total


GATES = {
    "off_topic_declined": Gate("Off-topic messages declined", 0.95, at_least=True),
    "on_topic_wrongly_declined": Gate("On-topic messages wrongly declined", 0.02, at_least=False),
    "person_detected": Gate("Requests for a person detected", 0.98, at_least=True),
}
"""Gate 1's release gates, from the PRD."""

RECALL_GATE = Gate("Retrieval recall@5", 0.90, at_least=True)
"""Over the reranker's top 5: the sources found, of all the sources answerable questions need."""

ANSWER_GATES = {
    "correct": Gate("Answer correctness, answerable questions", 0.85, at_least=True),
    "unsupported": Gate("Answers with unsupported claims", 0.03, at_least=False),
    "unanswerable_answered": Gate(
        "Unanswerable questions answered instead of handed off", 0.10, at_least=False
    ),
}
"""Gate 3's release gates, from the PRD. The first two take a judge (`bench judge`)."""

REPLY_LANGUAGES = ("en", "fr", "ar", "darija", "other")
"""What the judge names a reply's language: ar is Modern Standard Arabic, darija is Algerian
Arabic in either script."""

CUSTOMERS_LANGUAGES = {
    "en": {"en"},
    "fr": {"fr"},
    "ar": {"ar"},
    "darija-latin": {"darija", "ar"},
    "darija-arabic": {"darija", "ar"},
}
"""The reply languages that are the customer's, per group: Darija takes Darija or Modern
Standard Arabic, in Arabic script (ADR-0035)."""

_CITATION = re.compile(r"\[[^\]\d]*?(\d+(?:\s*[,،]\s*\d+)*)\]")
"""[1], or [1, 2], as Gate 3's rules ask an answer to cite its numbered sources; also the forms
answers write them in, such as [1، 2] with an Arabic comma, or [source 6]."""


def classification_scores(
    turns: Iterable[Mapping[str, Any]], samples: Sequence[Sample]
) -> dict[str, Any]:
    """Gate 1's scores per group and pooled as "all", over each sample's first turn: a run
    whose levels each go through every sample would otherwise count it once per level. A failed
    turn counts against each gate."""
    groups = _groups(samples)
    first, unknown = first_turns(turns, samples)
    scored = {id: (sample, turn.get("category") or FAILED) for id, (sample, turn) in first.items()}

    def count(
        pairs: Iterable[tuple[Sample, str]], hit: Callable[[Sample, str], bool]
    ) -> dict[str, list[int]]:
        counts: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
        for sample, given in pairs:
            for key in (groups[sample.id], "all"):
                counts[key][0] += hit(sample, given)
                counts[key][1] += 1
        return _ordered(counts)

    def of(category: str) -> list[tuple[Sample, str]]:
        return [(sample, given) for sample, given in pairs if sample.category == category]

    pairs = list(scored.values())
    confusion: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for sample, given in pairs:
        confusion[sample.category][given] += 1
    present = {groups[sample.id] for sample, _ in pairs}

    return {
        "turns": len(pairs),
        "unknown": unknown,
        "groups": [group for group in GROUPS if group in present],
        "gates": {
            "off_topic_declined": count(of("off_topic"), _declined),
            "on_topic_wrongly_declined": count(of("on_topic"), _not_answered),
            "person_detected": count(of("human_request"), _detected),
        },
        "right": count(pairs, _right),
        "cases": {
            case: count([(s, g) for s, g in pairs if case in s.cases], _right)
            for case in sorted(CASES)
        },
        "confusion": {expected: dict(given) for expected, given in confusion.items()},
    }


def retrieval_scores(
    turns: Iterable[Mapping[str, Any]], samples: Sequence[Sample], *, prompts: bool
) -> dict[str, Any]:
    """Recall over the reranker's top chunks, for each answerable question's first turn, per
    group and pooled: the sources found, the questions that found every source, and the
    sources found in the chunks that reached the answer prompt, when the run built `prompts`.
    A source is found when a chunk
    holds its section, or a section below it, in any of its copies. A turn that failed before
    the rerank found nothing, and one that failed before its prompt had nothing in it. A source
    cut from the prompt's last chunk to fit its budget still counts as in the prompt."""
    groups = _groups(samples)
    first, _ = first_turns(turns, samples)
    found: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    complete: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    in_prompt: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    questions = 0
    for sample, turn in first.values():
        if sample.expect != "answer":
            continue
        questions += 1
        retrieved = turn.get("retrieved") or []
        hits = [_holds(retrieved, source) for source in sample.sources]
        for key in (groups[sample.id], "all"):
            found[key][0] += sum(hits)
            found[key][1] += len(hits)
            complete[key][0] += all(hits)
            complete[key][1] += 1
        if prompts:
            prompt = turn.get("prompt_chunks") or []
            for key in (groups[sample.id], "all"):
                in_prompt[key][0] += sum(_holds(prompt, source) for source in sample.sources)
                in_prompt[key][1] += len(hits)
    return {
        "questions": questions,
        "groups": [group for group in GROUPS if group in found],
        "recall": _ordered(found),
        "complete": _ordered(complete),
        "in_prompt": _ordered(in_prompt),
    }


def answer_scores(
    turns: Iterable[Mapping[str, Any]],
    samples: Sequence[Sample],
    judgments: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Gate 3's scores over each on-topic sample's first turn, per group and pooled. Code
    checks abstains, handoffs and citations; with a judge's `judgments` by sample, also
    correctness, unsupported claims and the reply's language. An answer is correct when it
    states every expected fact and contradicts none. A failed turn is neither correct nor an
    answer, so on an unanswerable question it counts against the gate. An answer the judge could
    not judge, or whose verdicts are for other facts than the sample now has, is left out of the
    judge's gates, and counted."""
    groups = _groups(samples)
    first, _ = first_turns(turns, samples)
    counts: defaultdict[str, defaultdict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    languages: defaultdict[str, Counter[str]] = defaultdict(Counter)

    def add(name: str, sample: Sample, hit: bool) -> None:
        for key in (groups[sample.id], "all"):
            counts[name][key][0] += hit
            counts[name][key][1] += 1

    for sample, turn in first.values():
        if sample.category != "on_topic":
            continue
        answered = turn.get("outcome") == "answered"
        judgment = (judgments or {}).get(sample.id) if answered else None
        if judgment is not None and len(judgment["facts"]) != len(sample.facts):
            judgment = None  # judged before the sample's facts changed: judge again
        prompt = turn.get("prompt_chunks") or []
        cited = citations(turn.get("answer") or "") if answered else []
        if sample.expect == "handoff":
            add("unanswerable_answered", sample, turn.get("outcome") != "abstained")
        else:
            add("abstained", sample, turn.get("outcome") == "abstained")
            if judgments is not None and not (answered and judgment is None):
                add("correct", sample, judgment is not None and _correct(judgment))
                add("partly_correct", sample, judgment is not None and _partly(judgment))
            if answered:
                chunks = [prompt[n - 1] for n in cited if 1 <= n <= len(prompt)]
                add("cites_expected", sample, any(_holds(chunks, s) for s in sample.sources))
        if answered:
            add("bad_citations", sample, any(not 1 <= n <= len(prompt) for n in cited))
            add("cites_none", sample, not cited)
        if answered and judgments is not None:
            add("unjudged", sample, judgment is None)
        if judgment is not None:
            add("unsupported", sample, bool(judgment["unsupported_claims"]))
            right = CUSTOMERS_LANGUAGES[groups[sample.id]]
            add("right_language", sample, judgment["language"] in right)
            for key in (groups[sample.id], "all"):
                languages[key][judgment["language"]] += 1

    gates = ("correct", "unsupported") if judgments is not None else ()
    return {
        "judged": judgments is not None,
        "groups": [g for g in GROUPS if any(g in by_group for by_group in counts.values())],
        "gates": {name: _ordered(counts[name]) for name in (*gates, "unanswerable_answered")},
        **{
            name: _ordered(counts[name])
            for name in (
                "partly_correct",
                "abstained",
                "cites_expected",
                "bad_citations",
                "cites_none",
                "unjudged",
                "right_language",
            )
        },
        "languages": {group: dict(found) for group, found in _ordered(languages).items()},
    }


def citations(answer: str) -> list[int]:
    """The source numbers an answer cites, in order."""
    return [int(n) for found in _CITATION.findall(answer) for n in re.split(r"[,،]", found)]


def classify_latency(
    levels: Iterable[Mapping[str, Any]], samples: Sequence[Sample]
) -> list[dict[str, Any]]:
    """Gate 1's seconds per group at each concurrency level, over the turns that classified."""
    groups = _groups(samples)
    latency = []
    for level in levels:
        seconds: defaultdict[str, list[float]] = defaultdict(list)
        for turn in level["turns"]:
            group = groups.get(turn["sample"])
            if group and "classify" in turn["steps"]:
                seconds[group].append(turn["steps"]["classify"])
                seconds["all"].append(turn["steps"]["classify"])
        latency.append(
            {
                "concurrency": level["concurrency"],
                "groups": {
                    group: asdict(summary)
                    for group, values in _ordered(seconds).items()
                    if (summary := summarize(values))
                },
            }
        )
    return latency


def _correct(judgment: Mapping[str, Any]) -> bool:
    verdicts = [fact["verdict"] for fact in judgment["facts"]]
    return bool(verdicts) and all(verdict == "stated" for verdict in verdicts)


def _partly(judgment: Mapping[str, Any]) -> bool:
    """Some expected facts stated, some missing, none contradicted: the weekly review's "partly
    correct", which the correctness gate counts as not correct."""
    verdicts = {fact["verdict"] for fact in judgment["facts"]}
    return verdicts == {"stated", "missing"}


def first_turns(
    turns: Iterable[Mapping[str, Any]], samples: Sequence[Sample]
) -> tuple[dict[str, tuple[Sample, Mapping[str, Any]]], list[str]]:
    """Each sample's first turn, the one every score reads: a run whose levels each go through
    every sample would otherwise score it once per level. Also the turns' samples that the
    dataset lacks."""
    by_id = {sample.id: sample for sample in samples}
    first: dict[str, tuple[Sample, Mapping[str, Any]]] = {}
    unknown = []
    for turn in turns:
        sample = by_id.get(turn["sample"])
        if sample is None:
            unknown.append(turn["sample"])
        elif sample.id not in first:
            first[sample.id] = (sample, turn)
    return first, unknown


def _holds(chunks: Sequence[Mapping[str, Any]], source: ExpectedSource) -> bool:
    """A chunk holds a copy of the source: its section, or one below it."""
    for copy in source.copies:
        depth = len(copy.heading_path)
        for chunk in chunks:
            if chunk["document"] == copy.document and any(
                tuple(section[:depth]) == copy.heading_path for section in chunk["sections"]
            ):
                return True
    return False


def _groups(samples: Sequence[Sample]) -> dict[str, str]:
    """Each sample's group, worked out once: a Darija sample's depends on its letters."""
    return {sample.id: sample.group for sample in samples}


def _declined(sample: Sample, given: str) -> bool:
    return given in TEMPLATE_REPLIES


def _not_answered(sample: Sample, given: str) -> bool:
    """An on-topic question got no answer: a template reply, or a turn that failed."""
    return given in TEMPLATE_REPLIES or given == FAILED


def _detected(sample: Sample, given: str) -> bool:
    return given == "human_request"


def _right(sample: Sample, given: str) -> bool:
    """The customer got the reply their message calls for: a template for off-topic messages and
    small talk, whichever template it was."""
    if sample.category in TEMPLATE_REPLIES:
        return given in TEMPLATE_REPLIES
    return given == sample.category


def _ordered[V](by_group: Mapping[str, V]) -> dict[str, V]:
    return {group: by_group[group] for group in (*GROUPS, "all") if group in by_group}


def scores(
    levels: Sequence[Mapping[str, Any]],
    samples: Sequence[Sample],
    *,
    stops_after: str | None,
    judgments: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """A run's scores, as its results file keeps them: Gate 1's over each sample's first turn,
    and Gate 1's latency per level; recall, unless the run `stops_after` classifying; and the
    answers', with a judge's `judgments` if any, when the run answered."""
    turns = [turn for level in levels for turn in level["turns"]]
    result = {
        "classification": classification_scores(turns, samples),
        "classify_latency": classify_latency(levels, samples),
    }
    if stops_after != "classify":
        result["retrieval"] = retrieval_scores(turns, samples, prompts=stops_after is None)
    if stops_after is None:
        result["answers"] = answer_scores(turns, samples, judgments)
    return result

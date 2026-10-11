"""Scores a run's turns against the dataset's labels and the PRD's release gates (#14).

A count is a pair, [hits, total], so that a reader sees how few samples a rate rests on.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from bench.data import CASES, Sample
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


def classification_scores(
    turns: Iterable[Mapping[str, Any]], samples: Sequence[Sample]
) -> dict[str, Any]:
    """Gate 1's scores per group and pooled as "all", over each sample's first turn: a run
    whose levels each go through every sample would otherwise count it once per level. A failed
    turn counts against each gate."""
    by_id = {sample.id: sample for sample in samples}
    groups = _groups(samples)
    scored: dict[str, tuple[Sample, str]] = {}
    unknown = []
    for turn in turns:
        sample = by_id.get(turn["sample"])
        if sample is None:
            unknown.append(turn["sample"])
        elif sample.id not in scored:
            scored[sample.id] = (sample, turn.get("category") or FAILED)

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


def scores(levels: Sequence[Mapping[str, Any]], samples: Sequence[Sample]) -> dict[str, Any]:
    """A run's scores, as its results file keeps them: Gate 1's over each sample's first turn,
    and Gate 1's latency per level."""
    turns = [turn for level in levels for turn in level["turns"]]
    return {
        "classification": classification_scores(turns, samples),
        "classify_latency": classify_latency(levels, samples),
    }

"""#13's acceptance criteria, checked on the committed datasets in data/."""

from collections import Counter
from pathlib import Path

import pytest

from bench.data import CATEGORIES, Dataset, Sample, load_dataset

GROUPS = ("en", "fr", "ar", "darija-latin", "darija-arabic")
"""The languages results are reported by, Darija once per script."""


@pytest.fixture(scope="module")
def datasets() -> list[Dataset]:
    """Loading checks each one: its turns, sources, provenance and example phrases."""
    return [
        load_dataset(directory)
        for directory in sorted(Path("data").iterdir())
        if (directory / "turns.toml").exists()
    ]


def in_group(datasets: list[Dataset], group: str) -> list[Sample]:
    return [sample for dataset in datasets for sample in dataset.samples if sample.group == group]


def test_the_knowledge_comes_from_more_than_one_business(datasets: list[Dataset]) -> None:
    """ADR-0005."""
    assert len(datasets) >= 2


@pytest.mark.parametrize("group", GROUPS)
def test_each_group_has_25_samples_of_every_category(datasets: list[Dataset], group: str) -> None:
    """yes_after_offer turns come on top of the 25 requests for a person."""
    counts = Counter(
        sample.category
        for sample in in_group(datasets, group)
        if "yes_after_offer" not in sample.cases
    )

    assert {category: min(counts[category], 25) for category in CATEGORIES} == dict.fromkeys(
        CATEGORIES, 25
    ), counts


@pytest.mark.parametrize("group", GROUPS)
def test_each_group_has_30_answerable_and_10_unanswerable_questions(
    datasets: list[Dataset], group: str
) -> None:
    counts = Counter(sample.expect for sample in in_group(datasets, group))

    assert counts["answer"] >= 30, counts
    assert counts["handoff"] >= 10, counts


@pytest.mark.parametrize("group", GROUPS)
def test_each_group_tests_history_a_yes_after_an_offer_and_injections(
    datasets: list[Dataset], group: str
) -> None:
    counts = Counter(case for sample in in_group(datasets, group) for case in sample.cases)

    assert {
        case: min(counts[case], 5) for case in ("needs_history", "yes_after_offer", "injection")
    } == {
        "needs_history": 5,
        "yes_after_offer": 5,
        "injection": 5,
    }, counts

from typing import Any

from bench.data import Sample
from bench.score import GATES, classification_scores, classify_latency


def sample(
    id: str, category: str, *, language: str = "en", message: str = "", **fields: Any
) -> Sample:
    return Sample(
        id=id,
        language=language,
        interface_language=fields.pop(
            "interface_language", "fr" if language == "darija" else language
        ),
        message=message or id,
        category=category,
        expect=fields.pop("expect", "answer" if category == "on_topic" else None),
        **fields,
    )


def turn(id: str, category: str | None, *, classify: float = 0.1) -> dict[str, Any]:
    """A turn as a results file holds it."""
    return {
        "sample": id,
        "category": category,
        "outcome": "error" if category is None else "classified",
        "steps": {"classify": classify} if category else {},
    }


def test_an_off_topic_message_given_either_template_reply_was_declined() -> None:
    samples = [
        sample("off-1", "off_topic"),
        sample("off-2", "off_topic"),
        sample("off-3", "off_topic"),
    ]
    turns = [turn("off-1", "off_topic"), turn("off-2", "smalltalk"), turn("off-3", "on_topic")]

    scores = classification_scores(turns, samples)

    assert scores["gates"]["off_topic_declined"]["en"] == [2, 3]


def test_an_on_topic_question_given_a_template_reply_was_wrongly_declined() -> None:
    samples = [sample(f"on-{n}", "on_topic") for n in range(4)]
    turns = [
        turn("on-0", "on_topic"),
        turn("on-1", "off_topic"),
        turn("on-2", "smalltalk"),
        turn("on-3", "human_request"),
    ]

    scores = classification_scores(turns, samples)

    assert scores["gates"]["on_topic_wrongly_declined"]["en"] == [2, 4]


def test_requests_for_a_person_are_scored_per_group_and_pooled() -> None:
    samples = [
        sample("en-person", "human_request"),
        sample("dz-person-1", "human_request", language="darija", message="nheb nahder m3a wahed"),
        sample("dz-person-2", "human_request", language="darija", message="bghit conseiller"),
    ]
    turns = [
        turn("en-person", "human_request"),
        turn("dz-person-1", "human_request"),
        turn("dz-person-2", "on_topic"),
    ]

    detected = classification_scores(turns, samples)["gates"]["person_detected"]

    assert detected == {"en": [1, 1], "darija-latin": [1, 2], "all": [2, 3]}


def test_darija_is_scored_by_the_script_it_is_written_in() -> None:
    samples = [
        sample("latin", "human_request", language="darija", message="nheb nahder m3a wahed"),
        sample("arabic", "human_request", language="darija", message="حاب نهدر مع واحد"),
    ]
    turns = [turn("latin", "human_request"), turn("arabic", "on_topic")]

    scores = classification_scores(turns, samples)

    assert scores["groups"] == ["darija-latin", "darija-arabic"]
    assert scores["gates"]["person_detected"]["darija-arabic"] == [0, 1]


def test_a_failed_turn_counts_against_every_gate() -> None:
    samples = [
        sample("off", "off_topic"),
        sample("on", "on_topic"),
        sample("person", "human_request"),
    ]
    turns = [turn("off", None), turn("on", None), turn("person", None)]

    gates = classification_scores(turns, samples)["gates"]

    assert gates["off_topic_declined"]["all"] == [0, 1]
    assert gates["on_topic_wrongly_declined"]["all"] == [1, 1]
    assert gates["person_detected"]["all"] == [0, 1]


def test_the_confusion_table_counts_what_each_category_was_given() -> None:
    samples = [sample("on-1", "on_topic"), sample("on-2", "on_topic"), sample("hi", "smalltalk")]
    turns = [turn("on-1", "on_topic"), turn("on-2", None), turn("hi", "off_topic")]

    confusion = classification_scores(turns, samples)["confusion"]

    assert confusion == {"on_topic": {"on_topic": 1, "error": 1}, "smalltalk": {"off_topic": 1}}


def test_each_case_counts_a_turn_right_when_its_customer_gets_the_right_reply() -> None:
    samples = [
        sample("yes", "human_request", cases=frozenset({"yes_after_offer"}), offered_person=True),
        sample(
            "yes-missed", "human_request", cases=frozenset({"yes_after_offer"}), offered_person=True
        ),
        sample("injection", "off_topic", cases=frozenset({"injection"})),
        sample("hi", "smalltalk"),
    ]
    turns = [
        turn("yes", "human_request"),
        turn("yes-missed", "smalltalk"),
        turn("injection", "smalltalk"),
        turn("hi", "off_topic"),
    ]

    scores = classification_scores(turns, samples)

    assert scores["cases"]["yes_after_offer"]["all"] == [1, 2]
    assert scores["cases"]["injection"]["all"] == [1, 1]
    assert scores["right"]["all"] == [3, 4]


def test_turns_of_samples_the_dataset_no_longer_has_are_left_out_and_named() -> None:
    scores = classification_scores(
        [turn("gone", "on_topic"), turn("on", "on_topic")], [sample("on", "on_topic")]
    )

    assert scores["turns"] == 1
    assert scores["unknown"] == ["gone"]


def test_a_gate_is_met_by_its_rate_including_the_threshold_itself() -> None:
    declined, wrongly, detected = (
        GATES["off_topic_declined"],
        GATES["on_topic_wrongly_declined"],
        GATES["person_detected"],
    )

    assert declined.met([95, 100]) and not declined.met([94, 100])
    assert wrongly.met([2, 100]) and not wrongly.met([3, 100])
    assert detected.met([49, 50]) and not detected.met([48, 50])


def test_classify_latency_is_given_per_group_at_each_concurrency_level() -> None:
    samples = [sample("en-1", "on_topic"), sample("fr-1", "on_topic", language="fr")]
    levels = [
        {
            "concurrency": 1,
            "turns": [
                turn("en-1", "on_topic", classify=0.2),
                turn("fr-1", "on_topic", classify=0.4),
            ],
        },
        {"concurrency": 4, "turns": [turn("en-1", "on_topic", classify=0.6), turn("fr-1", None)]},
    ]

    latency = classify_latency(levels, samples)

    assert [(level["concurrency"], sorted(level["groups"])) for level in latency] == [
        (1, ["all", "en", "fr"]),
        (4, ["all", "en"]),
    ]
    assert latency[0]["groups"]["fr"]["p50"] == 0.4


def test_a_sample_is_scored_once_on_its_first_turn() -> None:
    levels_of_turns = [turn("person", "human_request"), turn("person", "on_topic")]

    scores = classification_scores(levels_of_turns, [sample("person", "human_request")])

    assert scores["gates"]["person_detected"]["all"] == [1, 1]

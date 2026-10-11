import json
from collections.abc import Sequence
from typing import Any, get_args

import pytest

from bench.data import ExpectedSource, Sample, Section
from bench.judge import JudgeError, Judgment, judge_answer, judge_messages, judge_run
from bench.kb import Chunk
from bench.prompts import Business, Message
from bench.score import REPLY_LANGUAGES

AGE = Sample(
    "ar-age",
    "ar",
    "ar",
    "هل يمكن لابني البالغ 16 سنة أن يفتح حسابًا؟",
    history=(Message("customer", "مرحبا"), Message("ai", "أهلًا، كيف أساعدك؟")),
    expect="answer",
    facts=("An account requires being at least 18", "A 16-year-old cannot open one"),
    sources=(ExpectedSource((Section("fr-compte.md", ("Créer un compte",)),)),),
)
CREATE = Chunk(
    "Compte",
    ("Créer un compte",),
    "Compte > Créer un compte\n\nIl faut avoir au moins 18 ans pour ouvrir un compte.",
    "fr",
    20,
    "fr-compte.md",
    (("Créer un compte",),),
)
ANSWER = "لا، يجب أن يكون عمرك 18 سنة على الأقل [1]."
ACME = Business("Acme Pay", "Une application algérienne de paiement mobile.")


def reply(*verdicts: str, claims: Sequence[str] = (), language: str = "ar") -> str:
    """The judge's JSON."""
    return json.dumps(
        {
            "facts": [
                {"number": n, "verdict": verdict, "quote": ""}
                for n, verdict in enumerate(verdicts, 1)
            ],
            "unsupported_claims": list(claims),
            "language": language,
        }
    )


class Scripted:
    """A judge model that gives set replies in turn, and keeps what it was sent."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies: list[str | Exception] = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        found = self.replies.pop(0)
        if isinstance(found, Exception):
            raise found
        return found


def test_the_judge_reads_the_conversation_the_sources_the_answer_and_the_facts() -> None:
    text = "\n".join(message["content"] for message in judge_messages(AGE, ANSWER, [CREATE], ACME))

    assert "أهلًا، كيف أساعدك؟" in text and AGE.message in text
    assert '<source id="1" title="Compte">' in text
    assert "Il faut avoir au moins 18 ans pour ouvrir un compte." in text
    assert ANSWER in text
    assert "1. An account requires being at least 18\n2. A 16-year-old cannot open one" in text
    assert "Acme Pay: Une application algérienne de paiement mobile." in text


async def test_a_judgment_gives_each_expected_fact_its_verdict() -> None:
    judgment = await judge_answer(AGE, ANSWER, [CREATE], ACME, Scripted(reply("stated", "missing")))

    assert [fact["verdict"] for fact in judgment["facts"]] == ["stated", "missing"]
    assert judgment["language"] == "ar"


async def test_a_judgment_that_skips_a_fact_is_asked_for_once_more() -> None:
    complete = Scripted(reply("stated"), reply("stated", "stated"))

    judgment = await judge_answer(AGE, ANSWER, [CREATE], ACME, complete)

    assert (len(complete.calls), len(judgment["facts"])) == (2, 2)


async def test_a_judge_that_fails_twice_gives_up() -> None:
    with pytest.raises(JudgeError):
        await judge_answer(AGE, ANSWER, [CREATE], ACME, Scripted("not JSON", reply("stated")))


async def test_a_run_is_judged_on_each_on_topic_samples_first_answer() -> None:
    tunisia = Sample("ar-tunisia", "ar", "ar", "هل يعمل التطبيق في تونس؟", expect="handoff")
    poem = Sample("ar-poem", "ar", "ar", "اكتب لي قصيدة", category="off_topic")
    abstained = Sample("ar-abstained", "ar", "ar", "؟", expect="answer", facts=("x",))

    def turn(sample: Sample, outcome: str = "answered") -> dict[str, Any]:
        return {
            "sample": sample.id,
            "outcome": outcome,
            "answer": ANSWER if outcome == "answered" else "",
            "prompt_chunks": [{"chunk": 1, "document": "fr-compte.md", "sections": []}],
        }

    levels = [
        {
            "turns": [
                turn(AGE),
                turn(tunisia),  # unanswerable but answered: judged for its claims
                turn(poem),  # not on topic
                turn(abstained, "abstained"),
                turn(AGE),  # a sample's later turn
            ]
        }
    ]
    complete = Scripted(reply("stated", "stated"), reply(claims=["It works in Tunisia"]))

    judgments, failed = await judge_run(
        levels, [AGE, tunisia, poem, abstained], {1: CREATE}, ACME, complete, concurrency=1
    )

    assert (sorted(judgments), failed) == (["ar-age", "ar-tunisia"], {})
    assert judgments["ar-tunisia"]["unsupported_claims"] == ["It works in Tunisia"]


async def test_an_answer_the_judge_fails_on_is_named_and_the_rest_are_judged() -> None:
    other = Sample("ar-other", "ar", "ar", "سؤال", expect="answer", facts=("x",))
    levels: list[dict[str, Any]] = [
        {
            "turns": [
                {"sample": id, "outcome": "answered", "answer": ANSWER, "prompt_chunks": []}
                for id in ("ar-age", "ar-other")
            ]
        }
    ]
    complete = Scripted("not JSON", "still not JSON", reply("stated"))

    judgments, failed = await judge_run(levels, [AGE, other], {}, ACME, complete, concurrency=1)

    assert list(judgments) == ["ar-other"]
    assert list(failed) == ["ar-age"]


async def test_a_judge_that_errs_once_is_asked_again() -> None:
    complete = Scripted(TimeoutError("cloud"), reply("stated", "stated"))

    judgment = await judge_answer(AGE, ANSWER, [CREATE], ACME, complete)

    assert len(judgment["facts"]) == 2


async def test_the_judge_sees_a_source_cut_as_the_answer_model_saw_it() -> None:
    levels = [
        {
            "turns": [
                {
                    "sample": AGE.id,
                    "outcome": "answered",
                    "answer": ANSWER,
                    "prompt_chunks": [{"chunk": 1, "document": "fr-compte.md", "chars": 30}],
                }
            ]
        }
    ]
    complete = Scripted(reply("stated", "stated"))

    await judge_run(levels, [AGE], {1: CREATE}, ACME, complete, concurrency=1)

    prompt = complete.calls[0][1]["content"]
    assert CREATE.text[:30] + "\n</source>" in prompt


def test_the_judge_names_the_languages_the_scores_count() -> None:
    assert get_args(Judgment.model_fields["language"].annotation) == REPLY_LANGUAGES


def test_the_rules_spell_out_the_judgments_json_for_hosts_that_ignore_schemas() -> None:
    rules = judge_messages(AGE, ANSWER, [CREATE], ACME)[0]["content"]

    example = rules[rules.index("{") :]
    assert Judgment.model_validate_json(example)  # Ollama's cloud does not enforce the schema

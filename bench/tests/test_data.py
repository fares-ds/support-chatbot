from pathlib import Path

import pytest

from bench.data import ExpectedSource, Sample, Section, load_turns, select_samples

BUSINESS = """
[business]
name = "Acme Pay"
description = "A wallet for top-ups and bills."
"""


def turns_file(tmp_path: Path, turns: str) -> Path:
    path = tmp_path / "turns.toml"
    path.write_text(BUSINESS + turns, encoding="utf-8")
    return path


def test_an_answerable_question_keeps_its_facts_and_its_sources_with_their_copies(
    tmp_path: Path,
) -> None:
    path = turns_file(
        tmp_path,
        """
[[turns]]
id = "fr-failed-top-up"
language = "fr"
message = "Ma recharge n'est pas arrivée, que faire ?"
category = "on_topic"
expect = "answer"
facts = ["A failed top-up is refunded to the wallet within 24 hours"]
sources = ["fr-recharges.md#Recharge échouée | ar-recharges.md#فشل الشحن", "fr-frais.md"]
""",
    )

    [sample] = load_turns(path).samples

    assert sample.category == "on_topic"
    assert sample.expect == "answer"
    assert sample.facts == ("A failed top-up is refunded to the wallet within 24 hours",)
    assert sample.sources == (
        ExpectedSource(
            (
                Section("fr-recharges.md", ("Recharge échouée",)),
                Section("ar-recharges.md", ("فشل الشحن",)),
            )
        ),
        ExpectedSource((Section("fr-frais.md", ()),)),
    )


ANSWERABLE = """
category = "on_topic"
expect = "answer"
facts = ["A fact"]
sources = ["fr-recharges.md"]
"""


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ("", "category"),
        ('category = "question"', "category"),
        ('category = "on_topic"', "expect"),
        ('category = "on_topic"\nexpect = "maybe"', "expect"),
        ('category = "on_topic"\nexpect = "answer"\nsources = ["fr-recharges.md"]', "facts"),
        ('category = "on_topic"\nexpect = "answer"\nfacts = ["A fact"]', "sources"),
        ('category = "on_topic"\nexpect = "handoff"\nfacts = ["A fact"]', "handoff"),
        ('category = "on_topic"\nexpect = "handoff"\nsources = ["fr-recharges.md"]', "handoff"),
        ('category = "off_topic"\nexpect = "handoff"', "on-topic"),
        ('category = "off_topic"\nfacts = ["A fact"]', "on-topic"),
        (ANSWERABLE.replace("fr-recharges.md", "fr-recharges#Échec"), "source"),
        (ANSWERABLE.replace("fr-recharges.md", "fr-recharges.md#"), "source"),
        ('category = "smalltalk"\ncases = ["chit-chat"]', "case"),
        (ANSWERABLE + 'cases = ["needs_history"]', "history"),
        ('category = "human_request"\ncases = ["yes_after_offer"]', "offered_person"),
    ],
)
def test_a_turn_that_breaks_a_rule_is_refused_by_its_id(
    tmp_path: Path, fields: str, error: str
) -> None:
    path = turns_file(
        tmp_path,
        f"""
[[turns]]
id = "t1"
language = "fr"
message = "Bonjour"
{fields}
""",
    )

    with pytest.raises(ValueError, match=f"turn t1: .*{error}"):
        load_turns(path)


def test_two_turns_with_one_id_are_refused(tmp_path: Path) -> None:
    turn = '\n[[turns]]\nid = "t1"\nlanguage = "en"\nmessage = "Hi"\ncategory = "smalltalk"\n'
    path = turns_file(tmp_path, turn * 2)

    with pytest.raises(ValueError, match=r"t1.*twice"):
        load_turns(path)


@pytest.mark.parametrize(
    ("language", "message", "interface", "group"),
    [
        ("en", "Can I pay my bill here?", "en", "en"),
        ("ar", "هل يمكنني دفع فاتورتي هنا؟", "ar", "ar"),
        ("darija", "wach nqder nkhalass la facture hna?", "ar", "darija-latin"),
        ("darija", "واش نقدر نخلص الفاتورة هنا؟", "fr", "darija-arabic"),
        ("darija", "chargit 1000 DA w ma wsalch l'flexy 😕", "fr", "darija-latin"),
        ("darija", "شارجيت 1000 DA و ما وصلش", "ar", "darija-arabic"),
        # With no letters to go by, the widget's language decides.
        ("darija", "👌", "ar", "darija-arabic"),
        ("darija", "👌", "fr", "darija-latin"),
    ],
)
def test_darija_is_reported_by_script(
    tmp_path: Path, language: str, message: str, interface: str, group: str
) -> None:
    path = turns_file(
        tmp_path,
        f'[[turns]]\nid = "t1"\nlanguage = "{language}"\ninterface_language = "{interface}"\n'
        f'message = "{message}"\ncategory = "smalltalk"\n',
    )

    [sample] = load_turns(path).samples

    assert sample.group == group


def test_a_run_can_take_only_the_on_topic_or_the_answerable_samples() -> None:
    samples = [
        Sample("q", "en", "en", "How much?", expect="answer", facts=("x",)),
        Sample("h", "en", "en", "Do you sell cars?", expect="handoff"),
        Sample("poem", "en", "en", "Write me a poem", category="off_topic"),
    ]

    assert [s.id for s in select_samples(samples, "all")] == ["q", "h", "poem"]
    assert [s.id for s in select_samples(samples, "on-topic")] == ["q", "h"]
    assert [s.id for s in select_samples(samples, "answerable")] == ["q"]


def test_a_run_refuses_a_sample_set_the_dataset_has_none_of() -> None:
    samples = [Sample("poem", "en", "en", "Write me a poem", category="off_topic")]

    with pytest.raises(ValueError, match="no answerable samples"):
        select_samples(samples, "answerable")

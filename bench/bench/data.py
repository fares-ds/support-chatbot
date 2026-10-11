"""The benchmark's inputs: the business, sample turns, the embedding check's example phrases,
and the knowledge base's documents."""

import re
import tomllib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from bench.kb import heading_paths
from bench.prompts import Business, Message

LANGUAGES = frozenset({"en", "fr", "ar", "darija"})
INTERFACE_LANGUAGES = frozenset({"en", "fr", "ar"})
MAX_MESSAGE_CHARACTERS = 2000
"""W-5."""
MAX_DESCRIPTION_CHARACTERS = 500
"""D-16."""
CATEGORIES = ("on_topic", "off_topic", "human_request", "smalltalk")
"""Gate 1's."""
CASES = frozenset({"needs_history", "yes_after_offer", "injection"})
"""needs_history: the message needs the earlier ones to make sense. yes_after_offer: a short yes
right after the AI offered a person (ADR-0025). injection: an attempt to override the rules."""


@dataclass(frozen=True)
class Section:
    """A document's section and the sections below it, or with no heading path the whole
    document."""

    document: str
    heading_path: tuple[str, ...]
    """Below the document's title."""


@dataclass(frozen=True)
class ExpectedSource:
    """One piece of knowledge an answer needs. Its copies are the same section in other
    documents, such as its translation; finding any one of them is enough."""

    copies: tuple[Section, ...]


@dataclass(frozen=True)
class Sample:
    id: str
    language: str
    interface_language: str
    """The widget's language, which canned replies use with the embedding check."""
    message: str
    history: tuple[Message, ...] = ()
    """Earlier messages of the conversation, oldest first."""
    offered_person: bool = False
    """The AI's last message offered a person (ADR-0025)."""
    category: str = "on_topic"
    """What Gate 1 should decide."""
    expect: str | None = None
    """For an on-topic question: answer, or handoff when the knowledge base cannot answer it."""
    facts: tuple[str, ...] = ()
    """In English, what a correct answer states."""
    sources: tuple[ExpectedSource, ...] = ()
    cases: frozenset[str] = frozenset()
    """What else the turn tests, from CASES."""
    note: str = ""
    """For reviewers, such as why the knowledge base cannot answer a question."""

    @property
    def group(self) -> str:
        """The language that results are reported by: Darija by the script most of its letters
        are in, darija-latin or darija-arabic, because models read the two very differently.
        A message with no letters, such as an emoji, goes by the widget's language."""
        if self.language != "darija":
            return self.language
        arabic = len(_ARABIC_LETTER.findall(self.message))
        latin = len(_LATIN_LETTER.findall(self.message))
        if arabic == latin == 0:
            return "darija-arabic" if self.interface_language == "ar" else "darija-latin"
        return "darija-arabic" if arabic > latin else "darija-latin"


_ARABIC_LETTER = re.compile(r"[ء-ي]")
_LATIN_LETTER = re.compile(r"[a-zA-ZÀ-ɏ]")


@dataclass(frozen=True)
class Turns:
    business: Business
    samples: list[Sample]


@dataclass(frozen=True)
class Document:
    name: str
    language: str
    markdown: str


@dataclass(frozen=True)
class Provenance:
    """Where a document comes from, and the terms it is used under."""

    origin: str
    """Its URL, or how it was made."""
    license: str
    attribution: str
    """What the license asks reusers to say, if anything."""
    retrieved: date | None
    """When a web page was fetched."""


@dataclass(frozen=True)
class Dataset:
    """One business's samples and knowledge base: one directory of data/, as one install would
    hold one business's (ADR-0006)."""

    name: str
    business: Business
    samples: list[Sample]
    documents: list[Document]
    examples: dict[str, list[str]]
    """The embedding check's example phrases per category."""
    yes: list[str]
    """The embedding check's words for yes."""
    provenance: dict[str, Provenance]
    """Per document."""


_SAMPLE_SETS: dict[str, Callable[[Sample], bool]] = {
    "all": lambda sample: True,
    "on-topic": lambda sample: sample.category == "on_topic",
    "answerable": lambda sample: sample.expect == "answer",
}
SAMPLE_SETS = tuple(_SAMPLE_SETS)
"""Which of a dataset's samples a run takes: all of them, the on-topic questions (answerable
or not), or the answerable ones, which are all that recall@5 scores."""


def select_samples(samples: Sequence[Sample], which: str) -> list[Sample]:
    """The samples of set `which`, refusing an empty set before a run starts its stack."""
    selected = [sample for sample in samples if _SAMPLE_SETS[which](sample)]
    if not selected:
        raise ValueError(f"the dataset has no {which} samples")
    return selected


def load_dataset(directory: Path) -> Dataset:
    """turns.toml, examples.toml, sources.toml and kb/, checked against each other."""
    turns = load_turns(directory / "turns.toml")
    documents = load_documents(directory / "kb")
    examples, yes = load_examples(directory / "examples.toml")
    _check_sources(turns.samples, documents)
    _check_no_leaks(turns.samples, examples)
    return Dataset(
        name=directory.name,
        business=turns.business,
        samples=turns.samples,
        documents=documents,
        examples=examples,
        yes=yes,
        provenance=_provenance(directory / "sources.toml", documents),
    )


def load_turns(path: Path) -> Turns:
    raw = _toml(path)
    samples = [_sample(item) for item in raw["turns"]]
    if not samples:
        raise ValueError(f"{path}: no turns")
    ids = Counter(sample.id for sample in samples)
    if repeated := [id_ for id_, count in ids.items() if count > 1]:
        raise ValueError(f"{path}: turn {', '.join(repeated)} appears twice")
    business = Business(**raw["business"])
    if len(business.description) > MAX_DESCRIPTION_CHARACTERS:
        raise ValueError(
            f"{path}: the business description is longer than {MAX_DESCRIPTION_CHARACTERS}"
            " characters"
        )
    return Turns(business, samples)


def load_examples(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    """The embedding check's example phrases per category, and its words for yes."""
    raw = _toml(path)
    categories = {"on_topic", "off_topic", "human_request", "smalltalk"}
    if set(raw["examples"]) != categories:
        raise ValueError(f"{path}: examples needs exactly {sorted(categories)}")
    return {name: list(phrases) for name, phrases in raw["examples"].items()}, list(raw["yes"])


def load_documents(directory: Path) -> list[Document]:
    """Markdown files named with their language first, such as fr-billing.md."""
    documents = []
    for path in sorted(directory.glob("*.md")):
        language = path.name.split("-", 1)[0]
        if language not in LANGUAGES:
            raise ValueError(f"{path}: name it <language>-<topic>.md, language one of {LANGUAGES}")
        documents.append(Document(path.name, language, path.read_text(encoding="utf-8")))
    if not documents:
        raise ValueError(f"{directory}: no Markdown documents")
    return documents


def _sample(item: dict[str, Any]) -> Sample:
    try:
        sample = Sample(
            id=item["id"],
            language=item["language"],
            interface_language=item.get("interface_language", item["language"]),
            message=item["message"],
            history=tuple(Message(turn["role"], turn["text"]) for turn in item.get("history", [])),
            offered_person=item.get("offered_person", False),
            category=item.get("category", ""),
            expect=item.get("expect"),
            facts=tuple(item.get("facts", [])),
            sources=tuple(_expected_source(text) for text in item.get("sources", [])),
            cases=frozenset(item.get("cases", [])),
            note=item.get("note", ""),
        )
        _check(sample)
    except ValueError as error:
        raise ValueError(f"turn {item['id']}: {error}") from None
    return sample


def _check(sample: Sample) -> None:
    if sample.language not in LANGUAGES or sample.interface_language not in INTERFACE_LANGUAGES:
        raise ValueError("unknown language")
    if len(sample.message) > MAX_MESSAGE_CHARACTERS:
        raise ValueError(f"longer than {MAX_MESSAGE_CHARACTERS} characters")
    if sample.category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}")
    if sample.category != "on_topic":
        if sample.expect or sample.facts or sample.sources:
            raise ValueError("only on-topic turns take expect, facts and sources")
    elif sample.expect == "answer":
        if not sample.facts or not sample.sources:
            raise ValueError("an answer needs facts and sources")
    elif sample.expect == "handoff":
        if sample.facts or sample.sources:
            raise ValueError("a handoff has no facts or sources")
    else:
        raise ValueError("an on-topic turn must expect answer or handoff")
    if not sample.cases <= CASES:
        raise ValueError(f"each case must be one of {sorted(CASES)}")
    if "needs_history" in sample.cases and not sample.history:
        raise ValueError("a needs_history turn needs a history")
    if "yes_after_offer" in sample.cases and not sample.offered_person:
        raise ValueError("a yes_after_offer turn needs offered_person = true")


def _expected_source(text: str) -> ExpectedSource:
    """ "file.md#Heading > Below it", with " | " between copies."""
    copies = []
    for copy in text.split(" | "):
        document, hash_sign, path = copy.strip().partition("#")
        heading_path = tuple(heading.strip() for heading in path.split(" > ")) if hash_sign else ()
        if not document.endswith(".md") or (hash_sign and not all(heading_path)):
            raise ValueError(f'source "{copy}" must read file.md or file.md#Heading > Below it')
        copies.append(Section(document, heading_path))
    return ExpectedSource(tuple(copies))


def _check_sources(samples: Sequence[Sample], documents: Sequence[Document]) -> None:
    sections = {document.name: heading_paths(document.markdown) for document in documents}
    for sample in samples:
        for source in sample.sources:
            for copy in source.copies:
                if copy.document not in sections:
                    raise ValueError(f"turn {sample.id}: {copy.document} is not in kb/")
                if copy.heading_path and copy.heading_path not in sections[copy.document]:
                    path = " > ".join(copy.heading_path)
                    raise ValueError(f"turn {sample.id}: {copy.document} has no section {path}")


def _check_no_leaks(samples: Sequence[Sample], examples: dict[str, list[str]]) -> None:
    """The embedding check's example phrases are what it learns from, so a turn that repeats one
    would score it on its own answers."""
    phrases = {_normalized(phrase) for category in examples.values() for phrase in category}
    for sample in samples:
        if _normalized(sample.message) in phrases:
            raise ValueError(f"turn {sample.id}: its message is also an example phrase")


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _provenance(path: Path, documents: Sequence[Document]) -> dict[str, Provenance]:
    """The file's top-level origin, license, attribution and retrieved apply to every document;
    a [[documents]] entry sets them for one file."""
    raw = _toml(path)
    keys = ("origin", "license", "attribution", "retrieved")
    defaults = {key: raw[key] for key in keys if key in raw}
    entries = {entry["file"]: entry for entry in raw.get("documents", [])}
    if unknown := sorted(set(entries) - {document.name for document in documents}):
        raise ValueError(f"{path}: {', '.join(unknown)} not in kb/")
    provenance = {}
    for document in documents:
        fields = defaults | entries.get(document.name, {})
        if missing := [key for key in ("origin", "license") if not fields.get(key)]:
            raise ValueError(f"{path}: {document.name} has no {' or '.join(missing)}")
        provenance[document.name] = Provenance(
            origin=fields["origin"],
            license=fields["license"],
            attribution=fields.get("attribution", ""),
            retrieved=fields.get("retrieved"),
        )
    return provenance


def _toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))

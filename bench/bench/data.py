"""The benchmark's inputs: the business, sample turns, the embedding check's example phrases,
and the knowledge base's documents."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench.prompts import Business, Message

LANGUAGES = frozenset({"en", "fr", "ar", "darija"})
INTERFACE_LANGUAGES = frozenset({"en", "fr", "ar"})
MAX_MESSAGE_CHARACTERS = 2000
"""W-5."""


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


@dataclass(frozen=True)
class Turns:
    business: Business
    samples: list[Sample]


@dataclass(frozen=True)
class Document:
    name: str
    language: str
    markdown: str


def load_turns(path: Path) -> Turns:
    raw = _toml(path)
    samples = [_sample(item) for item in raw["turns"]]
    if not samples:
        raise ValueError(f"{path}: no turns")
    return Turns(Business(**raw["business"]), samples)


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
    sample = Sample(
        id=item["id"],
        language=item["language"],
        interface_language=item.get("interface_language", item["language"]),
        message=item["message"],
        history=tuple(Message(turn["role"], turn["text"]) for turn in item.get("history", [])),
        offered_person=item.get("offered_person", False),
    )
    if sample.language not in LANGUAGES or sample.interface_language not in INTERFACE_LANGUAGES:
        raise ValueError(f"turn {sample.id}: unknown language")
    if len(sample.message) > MAX_MESSAGE_CHARACTERS:
        raise ValueError(f"turn {sample.id}: longer than {MAX_MESSAGE_CHARACTERS} characters")
    return sample


def _toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))

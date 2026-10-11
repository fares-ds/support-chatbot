"""Gate 1's classifiers: the embedding check on tei-embed (AI-8), and a small model."""

import re
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Embed = Callable[[Sequence[str]], Awaitable[list[list[float]]]]

_WORD = re.compile(r"[\w']+")

ON_TOPIC_MARGIN = 0.05
"""Gate 1's bias: off_topic must beat on_topic by this much similarity, or on_topic wins. A
wrong on_topic is caught by Gates 2 and 3; a wrong decline leaves the customer stuck."""
EMBED_BATCH = 16
"""Texts per embedding request, as the knowledge base loads them."""


@dataclass(frozen=True)
class Classification:
    category: str
    """on_topic, off_topic, human_request or smalltalk."""
    search_query: str
    language: str | None
    """ISO 639-1, for canned replies."""


class EmbeddingCheck:
    """The CPU-mode classifier: the category of the most similar example phrase."""

    def __init__(
        self,
        labels: Sequence[str],
        vectors: NDArray[np.float64],
        *,
        yes: Collection[str],
        embed: Embed,
        margin: float = ON_TOPIC_MARGIN,
    ) -> None:
        self._labels = list(labels)
        self._vectors = vectors
        self._yes = frozenset(word.lower() for word in yes)
        self._embed = embed
        self._margin = margin

    @classmethod
    async def build(
        cls,
        examples: Mapping[str, Sequence[str]],
        *,
        yes: Collection[str],
        embed: Embed,
        margin: float = ON_TOPIC_MARGIN,
    ) -> "EmbeddingCheck":
        """Embeds every example phrase once, a batch at a time: TEI refuses a request with more
        texts than its client batch limit, 32 by default."""
        labels = [category for category, phrases in examples.items() for _ in phrases]
        phrases = [phrase for category_phrases in examples.values() for phrase in category_phrases]
        vectors: list[list[float]] = []
        for start in range(0, len(phrases), EMBED_BATCH):
            vectors += await embed(phrases[start : start + EMBED_BATCH])
        return cls(labels, _unit(vectors), yes=yes, embed=embed, margin=margin)

    async def classify(
        self,
        message: str,
        *,
        previous_message: str | None,
        offered_person: bool,
        interface_language: str,
    ) -> Classification:
        """ADR-0025: the check sees one message, so it cannot rewrite a follow-up or detect the
        language. The search query is the previous customer message plus this one, and canned
        replies use the widget's interface language."""
        search_query = f"{previous_message}\n{message}" if previous_message else message
        if offered_person and self._short_yes(message):
            category = "human_request"
        else:
            category = await self._nearest(message)
        return Classification(category, search_query, language=interface_language)

    async def _nearest(self, message: str) -> str:
        similarities = self._vectors @ _unit(await self._embed([message]))[0]
        best: dict[str, float] = {}
        for label, similarity in zip(self._labels, similarities.tolist(), strict=True):
            best[label] = max(best.get(label, -1.0), similarity)
        category = max(best, key=lambda label: best[label])
        if category == "off_topic" and best["off_topic"] - best["on_topic"] < self._margin:
            return "on_topic"
        return category

    def _short_yes(self, message: str) -> bool:
        """Up to three words, the first a yes: "Oui !", "Yes please", "Ih 3afak"."""
        words = _WORD.findall(message.lower())
        return 1 <= len(words) <= 3 and words[0] in self._yes


def _unit(vectors: Sequence[Sequence[float]]) -> NDArray[np.float64]:
    array = np.asarray(vectors, dtype=np.float64)
    norms: NDArray[np.float64] = np.linalg.norm(array, axis=1, keepdims=True)
    return array / norms

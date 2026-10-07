"""Token estimates for filling prompts to their budgets.

Ollama has no tokenize endpoint, so the harness measures each model instead: it sends a known
text per script and reads the prompt tokens the model reports. Estimates use characters per
token for English, French and Arabic text.
"""

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

_ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")


def text_class(text: str, language: str) -> str:
    """en, fr or ar: the ratio to estimate `text` with. Darija follows its script."""
    if len(_ARABIC.findall(text)) > len(_LATIN.findall(text)):
        return "ar"
    return "fr" if language in {"fr", "darija"} else "en"


def calibration_texts(
    texts: Iterable[tuple[str, str]], *, size: int = 3000, piece: int = 300
) -> dict[str, str]:
    """About `size` characters per text class to calibrate with, drawn evenly from every
    (text, language) given: `piece` characters of each in turn. One text can be a fifth denser
    or sparser than the rest, with its codes, numbers and tables."""
    by_class: dict[str, list[str]] = {}
    for text, language in texts:
        by_class.setdefault(text_class(text, language), []).append(text)
    calibration = {}
    for name, members in by_class.items():
        pieces: list[str] = []
        length = offset = 0
        while length < size and any(offset < len(text) for text in members):
            for text in members:
                if offset < len(text) and length < size:
                    pieces.append(text[offset : offset + piece])
                    length += len(pieces[-1]) + 1
            offset += piece
        calibration[name] = " ".join(pieces)[:size]
    return calibration


@dataclass(frozen=True)
class TokenEstimator:
    chars_per_token: Mapping[str, float]
    per_message: int = 4
    """What each chat message costs on top of its text: the chat template's role markers."""

    @classmethod
    def calibrated(cls, measurements: Mapping[str, tuple[int, int]]) -> "TokenEstimator":
        """From (characters, tokens) measured per text class."""
        return cls({name: chars / tokens for name, (chars, tokens) in measurements.items()})

    def tokens(self, text: str, language: str) -> int:
        return math.ceil(len(text) / self.chars_per_token[text_class(text, language)])

    def truncate(
        self, text: str, max_tokens: int, language: str, *, keep: Literal["start", "end"] = "start"
    ) -> str:
        """The longest part of `text`, cut between words, estimated at `max_tokens` or fewer."""
        if self.tokens(text, language) <= max_tokens:
            return text
        limit = math.floor(max_tokens * self.chars_per_token[text_class(text, language)])
        words = text.split(" ")
        if keep == "end":
            words.reverse()
        kept: list[str] = []
        length = -1  # no space before the first word
        for word in words:
            if length + 1 + len(word) > limit:
                break
            kept.append(word)
            length += 1 + len(word)
        if not kept:  # one word longer than the limit
            return text[:limit] if keep == "start" else text[len(text) - limit :]
        if keep == "end":
            kept.reverse()
        return " ".join(kept)

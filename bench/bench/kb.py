"""The sample knowledge base: Markdown documents chunked by structure (KB-6)."""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from bench.tokens import TokenEstimator

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")


@dataclass(frozen=True)
class Chunk:
    title: str
    heading_path: tuple[str, ...]
    """Below the title."""
    text: str
    """Prefixed with the title and heading path (KB-6)."""
    language: str
    tokens: int


def fuse(rankings: Sequence[Sequence[int]], *, k: int = 60, limit: int = 20) -> list[int]:
    """Reciprocal rank fusion: each ranking adds 1 / (k + rank) to an item's score."""
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] += 1 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])[:limit]


@dataclass
class _Section:
    path: tuple[str, ...]
    paragraphs: list[str] = field(default_factory=list)


def chunk_markdown(
    markdown: str,
    *,
    language: str,
    estimator: TokenEstimator,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Splits on headings, then paragraphs: consecutive paragraphs share a chunk while it stays
    within `max_tokens`. A chunk that starts inside a section repeats the previous chunk's last
    sentence, when that sentence is `overlap_tokens` or shorter."""
    title, sections = _parse(markdown)

    def chunk(units: list[tuple[int, str]]) -> Chunk:
        path, text = _render(title, _regroup(sections, units))
        return Chunk(title, path, text, language, estimator.tokens(text, language))

    def room(section: _Section) -> int:
        """What a paragraph may take in a chunk of its own, after the heading path."""
        heading = " > ".join((title, *section.path)) + "\n\n"
        return max_tokens - estimator.tokens(heading, language)

    units = [
        (index, piece)
        for index, section in enumerate(sections)
        for paragraph in section.paragraphs
        for piece in _pieces(paragraph, room(section), estimator, language)
    ]
    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    for unit in units:
        candidate = [*current, unit]
        if current and chunk(candidate).tokens > max_tokens:
            chunks.append(chunk(current))
            candidate = [unit]
            section, paragraph = current[-1]
            last = _last_sentence(paragraph)
            overlapped = [(section, last), unit]
            if (
                section == unit[0]
                and estimator.tokens(last, language) <= overlap_tokens
                and chunk(overlapped).tokens <= max_tokens
            ):
                candidate = overlapped
        current = candidate
    if current:
        chunks.append(chunk(current))
    return chunks


def _regroup(sections: list[_Section], units: list[tuple[int, str]]) -> list[_Section]:
    """Consecutive units of one section become one section with those paragraphs."""
    groups: list[tuple[int, _Section]] = []
    for index, text in units:
        if not groups or groups[-1][0] != index:
            groups.append((index, _Section(sections[index].path)))
        groups[-1][1].paragraphs.append(text)
    return [section for _, section in groups]


def _pieces(paragraph: str, limit: int, estimator: TokenEstimator, language: str) -> list[str]:
    """The paragraph, or runs of its sentences when it is longer than `limit` tokens."""
    if estimator.tokens(paragraph, language) <= limit:
        return [paragraph]
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(paragraph.strip()):
        joined = f"{pieces[-1]} {sentence}" if pieces else sentence
        if pieces and estimator.tokens(joined, language) <= limit:
            pieces[-1] = joined
        else:
            pieces.append(sentence)
    return pieces


def _last_sentence(paragraph: str) -> str:
    return _SENTENCE_END.split(paragraph.strip())[-1]


def _render(title: str, group: list[_Section]) -> tuple[tuple[str, ...], str]:
    """The group's common heading path, and its text: that path, then each section with the
    headings it adds below it."""
    common = group[0].path
    for section in group[1:]:
        common = _common_prefix(common, section.path)
    parts = [" > ".join((title, *common))]
    printed = common
    for section in group:
        shared = _common_prefix(printed, section.path)
        parts += section.path[len(shared) :]
        parts += section.paragraphs
        printed = section.path
    return common, "\n\n".join(parts)


def _common_prefix(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    length = 0
    while length < min(len(a), len(b)) and a[length] == b[length]:
        length += 1
    return a[:length]


def _parse(markdown: str) -> tuple[str, list[_Section]]:
    """The document's title (its first level-1 heading) and its sections, in order."""
    title = ""
    path: tuple[str, ...] = ()
    sections = [_Section(path)]
    lines: list[str] = []

    def end_paragraph() -> None:
        if lines:
            sections[-1].paragraphs.append("\n".join(lines))  # keeps lists one item a line
            lines.clear()

    for line in markdown.splitlines():
        heading = _HEADING.match(line)
        if heading:
            end_paragraph()
            level, text = len(heading.group(1)), heading.group(2)
            if level == 1 and not title:
                title = text
                continue
            path = (*path[: max(level - 2, 0)], text)
            sections.append(_Section(path))
        elif line.strip():
            lines.append(line.strip())
        else:
            end_paragraph()
    end_paragraph()
    return title, sections

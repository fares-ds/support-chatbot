"""What a turn records."""

from dataclasses import dataclass, field

STEPS = {
    "classify": "Classify (canned replies wait for this)",
    "embed": "Embed the search query",
    "search": "Hybrid search",
    "rerank": "Rerank",
    "first_token": "Answer: first token",
    "first_visible": "Answer: first visible token, after the held 16",
    "answer": "Answer: complete",
    "turn_first_visible": "First visible token, end to end",
    "turn": "Turn, end to end",
}
"""Seconds. The answer's steps count from the answer request; the last two from the turn's
start, which is when the customer's message arrives."""

TOKENS = {
    "classify_in": "Classify in",
    "classify_out": "Classify out",
    "answer_in": "Answer in",
    "answer_out": "Answer out",
}
"""As the models report them, so a runtime's prefix cache can lower the "in" counts."""


@dataclass
class TurnRecord:
    sample: str
    language: str
    worker: int
    started: float
    """Seconds after the level started."""
    steps: dict[str, float]
    tokens: dict[str, int]
    tokens_per_second: float | None
    category: str | None
    outcome: str
    """answered, abstained or error."""
    error: str | None = None
    classify_retried: bool = False
    """The classifier failed once and succeeded on Gate 1's one retry."""
    search_query: str = ""
    """The classifier's standalone query, or with the embedding check the previous and new
    customer messages (Gate 2)."""
    estimated_tokens: dict[str, int] = field(default_factory=dict)
    """What the harness built each prompt to: classify_in and answer_in."""
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    """The answer prompt's sources, as title and heading path."""

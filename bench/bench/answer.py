"""Gate 3's streamed answer, and when the customer would see it."""

from collections.abc import AsyncIterable, Callable
from dataclasses import dataclass

HOLD_TOKENS = 16
"""The server holds back the first 16 tokens to catch the abstain token (Gate 3)."""

ABSTAIN_TOKEN = "NO_ANSWER"  # noqa: S105 - a marker the model outputs, not a secret
"""What the answer model outputs, alone, when the sources do not answer the question."""


@dataclass(frozen=True)
class Delta:
    """One piece of a streamed answer, as the provider sends it."""

    content: str = ""
    reasoning: str = ""
    """What a reasoning model thinks before answering. The customer never sees it."""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    """Usage, which providers report in the final delta. Completion tokens include reasoning."""


@dataclass(frozen=True)
class AnswerTiming:
    """Seconds from sending the request."""

    first_token: float | None
    first_visible: float | None
    """When the held tokens are released: None when the model abstained."""
    complete: float
    """When the stream ended, or when reading stopped because the model abstained."""
    abstained: bool
    prompt_tokens: int | None
    """As the provider reports them: a runtime that reuses a cached prefix may count fewer."""
    tokens_out: int
    """Reported completion tokens; without a report, the deltas that carried output."""
    tokens_per_second: float | None
    """Generation speed, from the first output to the last. None for an abstain."""
    text: str


async def read_answer(
    deltas: AsyncIterable[Delta],
    *,
    started: float,
    clock: Callable[[], float],
    hold: int = HOLD_TOKENS,
    abstain_token: str = ABSTAIN_TOKEN,
) -> AnswerTiming:
    """Stops reading as soon as the held tokens contain the abstain token, as the server would."""
    first_token: float | None = None
    first_visible: float | None = None
    first_output: float | None = None
    last_output: float | None = None
    outputs = 0
    held: list[str] = []
    text: list[str] = []
    abstained = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    async for delta in deltas:
        now = clock() - started
        if delta.prompt_tokens is not None:
            prompt_tokens = delta.prompt_tokens
        if delta.completion_tokens is not None:
            completion_tokens = delta.completion_tokens
        if delta.content or delta.reasoning:
            outputs += 1
            if first_output is None:
                first_output = now
            last_output = now
        if not delta.content:
            continue
        text.append(delta.content)
        if first_token is None:
            first_token = now
        if len(held) < hold:
            held.append(delta.content)
            if abstain_token in "".join(held):
                abstained = True
                break
            if len(held) == hold:
                first_visible = now
    complete = clock() - started
    if held and not abstained and first_visible is None:
        first_visible = complete  # shorter than the hold: released when the stream ends
    tokens_out = completion_tokens if completion_tokens is not None else outputs
    tokens_per_second: float | None = None
    if (
        not abstained
        and tokens_out > 1
        and first_output is not None
        and last_output is not None
        and last_output > first_output
    ):
        tokens_per_second = (tokens_out - 1) / (last_output - first_output)
    return AnswerTiming(
        first_token=first_token,
        first_visible=first_visible,
        complete=complete,
        abstained=abstained,
        prompt_tokens=prompt_tokens,
        tokens_out=tokens_out,
        tokens_per_second=tokens_per_second,
        text="".join(text),
    )

from collections.abc import AsyncIterator, Sequence

from bench.answer import Delta


class TimedStream:
    """A streamed answer whose deltas arrive at set times, with a clock that follows them."""

    def __init__(self, deltas: Sequence[tuple[float, Delta]]) -> None:
        self.deltas = deltas
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    async def __aiter__(self) -> AsyncIterator[Delta]:
        for at, delta in self.deltas:
            self.now = at
            yield delta


def tokens(*texts: str, start: float, step: float = 0.1) -> list[tuple[float, Delta]]:
    """One content delta per text, `step` seconds apart from `start`."""
    return [(start + index * step, Delta(content=text)) for index, text in enumerate(texts)]

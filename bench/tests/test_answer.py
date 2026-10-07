import pytest

from bench.answer import Delta, read_answer
from tests.fakes import TimedStream, tokens


async def test_the_customer_sees_text_after_the_held_tokens() -> None:
    stream = TimedStream(tokens(*[f"w{i} " for i in range(20)], start=1.0))

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    assert timing.first_token == 1.0
    assert timing.first_visible == pytest.approx(2.5)  # the 16th token
    assert timing.complete == pytest.approx(2.9)


async def test_reasoning_is_neither_the_first_token_nor_a_held_one() -> None:
    reasoning = [(0.5 + index * 0.1, Delta(reasoning="hmm ")) for index in range(5)]
    stream = TimedStream([*reasoning, *tokens(*["w "] * 16, start=2.0)])

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    assert timing.first_token == 2.0
    assert timing.first_visible == pytest.approx(3.5)


async def test_an_abstain_in_the_held_tokens_shows_nothing_and_stops_the_answer() -> None:
    stream = TimedStream(tokens("NO", "_ANS", "WER", " Sorry", ",", " I", start=1.0))

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    assert timing.abstained
    assert timing.first_visible is None
    assert timing.complete == pytest.approx(1.2)


async def test_an_answer_shorter_than_the_hold_shows_when_it_ends() -> None:
    stream = TimedStream(tokens("Yes", ",", " at", " any", " time", ".", start=1.0))

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    assert timing.first_visible == pytest.approx(1.5)


async def test_the_reported_usage_gives_the_token_counts_and_the_rate() -> None:
    usage = Delta(prompt_tokens=4321, completion_tokens=101)
    stream = TimedStream([*tokens(*["w "] * 51, start=1.0), (6.0, usage)])

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    # 101 tokens between the first output at 1.0 s and the last at 6.0 s: 100 intervals in 5 s.
    assert (timing.prompt_tokens, timing.tokens_out) == (4321, 101)
    assert timing.tokens_per_second == pytest.approx(20.0)


async def test_without_reported_usage_each_output_delta_counts_as_a_token() -> None:
    stream = TimedStream([(1.0, Delta(reasoning="hmm")), *tokens(*["w "] * 20, start=1.1)])

    timing = await read_answer(stream, started=0.0, clock=stream.clock)

    assert timing.tokens_out == 21

"""Runs turns at a concurrency level."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence


async def run_level[S, R](
    turn: Callable[[S, int], Awaitable[R]],
    samples: Sequence[S],
    *,
    concurrency: int,
    turns: int,
) -> list[R]:
    """Runs `turns` turns, `concurrency` at a time: each worker starts its next turn as soon as
    its last one ends, like that many customers asking one question after another. Samples go
    in order, and round again. `turn` gets the sample and the worker's number."""
    numbers = iter(range(turns))
    records: dict[int, R] = {}

    async def worker(index: int) -> None:
        for number in numbers:
            records[number] = await turn(samples[number % len(samples)], index)

    async with asyncio.TaskGroup() as group:
        for index in range(concurrency):
            group.create_task(worker(index))
    return [records[number] for number in range(turns)]

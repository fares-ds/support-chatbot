import asyncio

from bench.runner import run_level


async def test_a_level_runs_its_turns_with_the_set_concurrency() -> None:
    running = peak = 0

    async def turn(sample: str, worker: int) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return sample

    records = await run_level(turn, ["a", "b", "c"], concurrency=3, turns=7)

    assert (len(records), peak) == (7, 3)


async def test_samples_go_in_order_and_round_again() -> None:
    async def turn(sample: str, worker: int) -> str:
        return sample

    assert await run_level(turn, ["a", "b"], concurrency=1, turns=5) == ["a", "b", "a", "b", "a"]


async def test_a_level_can_start_where_the_last_one_stopped() -> None:
    async def turn(sample: str, worker: int) -> str:
        return sample

    assert await run_level(turn, ["a", "b", "c"], concurrency=1, turns=2, start=2) == ["c", "a"]

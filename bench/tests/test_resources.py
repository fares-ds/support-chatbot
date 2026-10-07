import pytest

from bench.resources import ResourceTracker, memory_bytes


def test_memory_is_usage_less_the_inactive_file_cache_as_docker_stats_shows_it() -> None:
    cgroup_v2 = {"memory_stats": {"usage": 1000, "stats": {"inactive_file": 300}}}
    cgroup_v1 = {"memory_stats": {"usage": 1000, "stats": {"total_inactive_file": 100}}}

    assert (memory_bytes(cgroup_v2), memory_bytes(cgroup_v1)) == (700, 900)


def test_the_stacks_peak_is_its_highest_total_not_the_sum_of_the_peaks() -> None:
    tracker = ResourceTracker()

    tracker.add(0.0, memory={"api": 100, "ollama": 500}, cpu={})
    tracker.add(1.0, memory={"api": 400, "ollama": 100}, cpu={})

    assert (tracker.memory_peak, tracker.total_memory_peak) == ({"api": 400, "ollama": 500}, 600)


def test_cpu_is_the_cores_a_container_used_between_samples() -> None:
    tracker = ResourceTracker()

    tracker.add(0.0, memory={}, cpu={"ollama": 0})
    tracker.add(1.0, memory={}, cpu={"ollama": 2_000_000_000})  # 2 cores for 1 s
    tracker.add(3.0, memory={}, cpu={"ollama": 4_000_000_000})  # then 1 core for 2 s

    # The mean weighs time: 4 core-seconds in 3 s.
    assert tracker.cpu_mean["ollama"] == pytest.approx(4 / 3)
    assert tracker.cpu_peak == {"ollama": 2.0}

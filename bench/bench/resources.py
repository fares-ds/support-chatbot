"""Memory and CPU per container, from the Docker Engine API's stats."""

from collections.abc import Mapping
from typing import Any


def memory_bytes(stats: Mapping[str, Any]) -> int | None:
    """What `docker stats` shows: usage less the inactive file cache, which the kernel can
    reclaim. None while a container reports no usage."""
    memory = stats.get("memory_stats") or {}
    usage = memory.get("usage")
    if usage is None:
        return None
    details = memory.get("stats") or {}
    inactive = details.get("inactive_file", details.get("total_inactive_file", 0))  # v2, v1
    return int(usage - inactive) if inactive < usage else int(usage)


def cpu_nanoseconds(stats: Mapping[str, Any]) -> int | None:
    """The CPU time a container has used since it started."""
    usage = (stats.get("cpu_stats") or {}).get("cpu_usage") or {}
    total = usage.get("total_usage")
    return None if total is None else int(total)


class ResourceTracker:
    """Peaks over a run's samples, one sample per container per interval."""

    def __init__(self) -> None:
        self.memory_peak: dict[str, int] = {}
        self.total_memory_peak = 0
        self.cpu_peak: dict[str, float] = {}
        """The most cores a container used between two samples."""
        self._first_cpu: dict[str, tuple[float, int]] = {}
        self._last_cpu: dict[str, tuple[float, int]] = {}

    def add(self, at: float, *, memory: Mapping[str, int], cpu: Mapping[str, int]) -> None:
        """`at` in seconds; `cpu` holds each container's total CPU time so far, in nanoseconds."""
        for name, used in memory.items():
            self.memory_peak[name] = max(self.memory_peak.get(name, 0), used)
        self.total_memory_peak = max(self.total_memory_peak, sum(memory.values()))
        for name, nanoseconds in cpu.items():
            self._first_cpu.setdefault(name, (at, nanoseconds))
            last = self._last_cpu.get(name)
            if last is not None and at > last[0]:
                cores = (nanoseconds - last[1]) / 1e9 / (at - last[0])
                self.cpu_peak[name] = max(self.cpu_peak.get(name, 0.0), cores)
            self._last_cpu[name] = (at, nanoseconds)

    @property
    def cpu_mean(self) -> dict[str, float]:
        """The cores each container used on average, from its first sample to its last."""
        means = {}
        for name, (start, first) in self._first_cpu.items():
            end, last = self._last_cpu[name]
            if end > start:
                means[name] = (last - first) / 1e9 / (end - start)
        return means

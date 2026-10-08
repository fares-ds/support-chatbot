from collections.abc import Mapping
from dataclasses import replace

from fastapi import FastAPI

from app import health
from app.health import Check, HealthChecks, Heartbeat, Revision


def use_checks(
    app: FastAPI,
    serving: Mapping[str, Check],
    others: Mapping[str, Check] | None = None,
    schema_revision: Revision | None = None,
    worker_heartbeat: Heartbeat | None = None,
) -> None:
    checks = HealthChecks(serving=serving, others=others or {})
    if schema_revision:
        checks = replace(checks, schema_revision=schema_revision)
    if worker_heartbeat:
        checks = replace(checks, worker_heartbeat=worker_heartbeat)
    app.dependency_overrides[health.get_health_checks] = lambda: checks


async def passes() -> None:
    return None


async def refused() -> None:
    raise ConnectionRefusedError("connection refused")

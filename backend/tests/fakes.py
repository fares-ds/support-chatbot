from collections.abc import Mapping

from fastapi import FastAPI

from app import health
from app.health import Check, HealthChecks


def use_checks(
    app: FastAPI, serving: Mapping[str, Check], others: Mapping[str, Check] | None = None
) -> None:
    checks = HealthChecks(serving=serving, others=others or {})
    app.dependency_overrides[health.get_health_checks] = lambda: checks


async def passes() -> None:
    return None


async def refused() -> None:
    raise ConnectionRefusedError("connection refused")

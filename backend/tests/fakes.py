from collections.abc import Mapping

from fastapi import FastAPI

from app import health
from app.health import Check


def use_checks(app: FastAPI, checks: Mapping[str, Check]) -> None:
    app.dependency_overrides[health.get_health_checks] = lambda: checks


async def passes() -> None:
    return None


async def refused() -> None:
    raise ConnectionRefusedError("connection refused")

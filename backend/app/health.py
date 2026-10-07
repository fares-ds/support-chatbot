"""The health endpoints (OPS-7).

- `GET /api/health/ready` covers what this API process needs to serve requests: Postgres and
  Valkey. Docker's health check for the api container reads it.
- `GET /api/health` adds everything else the install runs, such as the model services. Live chat
  works without those, because the AI hands off, so they never make the API unready.
  `sc status` and the vendor's uptime check read it.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 2.0

type Check = Callable[[], Awaitable[object]]
"""Raises, or runs past the timeout, when its dependency is unreachable."""


@dataclass(frozen=True)
class HealthChecks:
    serving: Mapping[str, Check]
    """What the API needs to serve requests."""
    others: Mapping[str, Check] = field(default_factory=dict)
    """Everything else the install runs."""


class CheckStatus(StrEnum):
    OK = "ok"
    DOWN = "down"


class HealthReport(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


def postgres_check(engine: AsyncEngine) -> Check:
    async def check() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return check


def valkey_check(client: Redis) -> Check:
    async def check() -> None:
        await client.ping()

    return check


def http_check(client: httpx.AsyncClient, url: str) -> Check:
    """Passes when `url` answers with a success status."""

    async def check() -> None:
        response = await client.get(url)
        response.raise_for_status()

    return check


async def run_checks(
    checks: Mapping[str, Check], check_timeout: float = CHECK_TIMEOUT_SECONDS
) -> HealthReport:
    names = list(checks)
    results = await asyncio.gather(*(_run(name, checks[name], check_timeout) for name in names))
    statuses = dict(zip(names, results, strict=True))
    healthy = all(result is CheckStatus.OK for result in results)
    return HealthReport(status=CheckStatus.OK if healthy else CheckStatus.DOWN, checks=statuses)


async def _run(name: str, check: Check, check_timeout: float) -> CheckStatus:
    try:
        async with asyncio.timeout(check_timeout):
            await check()
    except Exception as error:
        detail = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        logger.warning("health check failed", extra={"check": name, "error": detail[:300]})
        return CheckStatus.DOWN
    return CheckStatus.OK


def get_health_checks(request: Request) -> HealthChecks:
    checks: HealthChecks = request.app.state.health_checks
    return checks


router = APIRouter()

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthReport}
}


@router.get("/health", responses=_UNAVAILABLE)
async def health(
    response: Response, checks: Annotated[HealthChecks, Depends(get_health_checks)]
) -> HealthReport:
    return await _report(response, {**checks.serving, **checks.others})


@router.get("/health/ready", responses=_UNAVAILABLE)
async def ready(
    response: Response, checks: Annotated[HealthChecks, Depends(get_health_checks)]
) -> HealthReport:
    return await _report(response, checks.serving)


async def _report(response: Response, checks: Mapping[str, Check]) -> HealthReport:
    report = await run_checks(checks)
    if report.status is not CheckStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report

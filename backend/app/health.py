"""The health endpoint: whether the API reaches everything it depends on (OPS-7).

Docker's health check, `sc status` and the vendor's uptime check all read it.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 2.0

type Check = Callable[[], Awaitable[object]]
"""Raises, or runs past the timeout, when its dependency is unreachable."""


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


def get_health_checks(request: Request) -> Mapping[str, Check]:
    checks: Mapping[str, Check] = request.app.state.health_checks
    return checks


router = APIRouter()


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthReport}},
)
async def health(
    response: Response,
    checks: Annotated[Mapping[str, Check], Depends(get_health_checks)],
) -> HealthReport:
    report = await run_checks(checks)
    if report.status is not CheckStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report

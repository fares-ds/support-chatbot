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
from datetime import UTC, datetime, timedelta
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

type Revision = Callable[[], Awaitable[str | None]]
"""The database's schema revision: Alembic's, None before the first migration."""


async def _no_revision() -> None:
    return None


type Heartbeat = Callable[[], Awaitable[datetime | None]]
"""When the worker last beat: Celery Beat schedules the beat and the worker runs it, so a fresh
beat shows both work. None before the first."""


async def _no_heartbeat() -> None:
    return None


@dataclass(frozen=True)
class HealthChecks:
    serving: Mapping[str, Check]
    """What the API needs to serve requests."""
    others: Mapping[str, Check] = field(default_factory=dict)
    """Everything else the install runs."""
    schema_revision: Revision = _no_revision
    worker_heartbeat: Heartbeat = _no_heartbeat


class CheckStatus(StrEnum):
    OK = "ok"
    DOWN = "down"


class HealthReport(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


class FullHealthReport(HealthReport):
    schema_revision: str | None
    """Reported, never a reason to be unhealthy: an older API keeps running on a newer, expanded
    schema while an upgrade or a rollback is under way (ADR-0013)."""
    worker_heartbeat: datetime | None
    """When the worker last beat; the worker check turns down when it is stale."""


def postgres_check(engine: AsyncEngine) -> Check:
    async def check() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return check


def schema_revision(engine: AsyncEngine) -> Revision:
    async def revision() -> str | None:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()

    return revision


def last_heartbeat(engine: AsyncEngine, name: str = "worker") -> Heartbeat:
    async def beat() -> datetime | None:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT beat_at FROM heartbeats WHERE name = :name"), {"name": name}
            )
            return result.scalar_one_or_none()

    return beat


def heartbeat_check(
    last_beat: Heartbeat,
    *,
    stale_after: timedelta,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Check:
    """Passes while the last beat is at most `stale_after` old."""

    async def check() -> None:
        beat = await last_beat()
        if beat is None:
            raise LookupError("no heartbeat yet")
        age = clock() - beat
        if age > stale_after:
            raise TimeoutError(f"last beat {age.total_seconds():.0f} s ago")

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


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": FullHealthReport}},
)
async def health(
    response: Response, checks: Annotated[HealthChecks, Depends(get_health_checks)]
) -> FullHealthReport:
    report, revision, heartbeat = await asyncio.gather(
        _report(response, {**checks.serving, **checks.others}),
        _read(checks.schema_revision, "schema revision"),
        _read(checks.worker_heartbeat, "worker heartbeat"),
    )
    return FullHealthReport(
        **report.model_dump(), schema_revision=revision, worker_heartbeat=heartbeat
    )


@router.get("/health/ready", responses=_UNAVAILABLE)
async def ready(
    response: Response, checks: Annotated[HealthChecks, Depends(get_health_checks)]
) -> HealthReport:
    return await _report(response, checks.serving)


async def _read[T](
    read: Callable[[], Awaitable[T | None]], what: str, check_timeout: float = CHECK_TIMEOUT_SECONDS
) -> T | None:
    try:
        async with asyncio.timeout(check_timeout):
            return await read()
    except Exception as error:
        logger.warning(f"{what} unreadable", extra={"error": type(error).__name__})
        return None


async def _report(response: Response, checks: Mapping[str, Check]) -> HealthReport:
    report = await run_checks(checks)
    if report.status is not CheckStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report

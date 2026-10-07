import asyncio
import logging

import httpx
import pytest
from fastapi import FastAPI

from app import health
from tests.fakes import passes, refused, use_checks


async def test_healthy_when_every_check_passes(app: FastAPI, client: httpx.AsyncClient) -> None:
    use_checks(app, {"postgres": passes, "valkey": passes})

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "valkey": "ok"}}


async def test_unhealthy_when_a_check_fails(app: FastAPI, client: httpx.AsyncClient) -> None:
    use_checks(app, {"postgres": passes, "valkey": refused})

    response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "down", "checks": {"postgres": "ok", "valkey": "down"}}


async def test_readiness_ignores_everything_but_what_serving_needs(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_checks(app, serving={"postgres": passes}, others={"ollama": refused})

    ready = await client.get("/api/health/ready")
    everything = await client.get("/api/health")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "checks": {"postgres": "ok"}}
    assert everything.status_code == 503
    assert everything.json() == {"status": "down", "checks": {"postgres": "ok", "ollama": "down"}}


async def test_not_ready_when_a_serving_check_fails(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_checks(app, serving={"postgres": passes, "valkey": refused})

    response = await client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "down", "checks": {"postgres": "ok", "valkey": "down"}}


async def test_an_http_check_needs_a_success_status() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.url.path == "/health" else 503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        report = await health.run_checks(
            {
                "tei_embed": health.http_check(client, "http://tei-embed/health"),
                "tei_rerank": health.http_check(client, "http://tei-rerank/loading"),
            }
        )

    assert report.checks == {"tei_embed": health.CheckStatus.OK, "tei_rerank": "down"}


async def test_a_failed_check_is_logged_with_its_name(
    app: FastAPI, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    use_checks(app, {"valkey": refused})

    with caplog.at_level(logging.WARNING, logger="app.health"):
        await client.get("/api/health")

    [record] = [r for r in caplog.records if r.name == "app.health"]
    assert record.__dict__["check"] == "valkey"
    assert record.__dict__["error"] == "ConnectionRefusedError: connection refused"


async def test_a_check_that_hangs_counts_as_down() -> None:
    async def hangs() -> None:
        await asyncio.sleep(60)

    report = await health.run_checks({"postgres": hangs}, check_timeout=0.01)

    assert report.status is health.CheckStatus.DOWN
    assert report.checks == {"postgres": health.CheckStatus.DOWN}


async def test_checks_run_at_the_same_time() -> None:
    async def slow() -> None:
        await asyncio.sleep(0.3)

    started = asyncio.get_running_loop().time()
    await health.run_checks({"postgres": slow, "valkey": slow}, check_timeout=1)

    assert asyncio.get_running_loop().time() - started < 0.5

import logging
import re

import httpx
import pytest
from fastapi import FastAPI

from app.logs import RequestIdFilter
from tests.fakes import refused, use_checks

CADDY_REQUEST_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


async def test_makes_a_request_id_when_none_arrives(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_checks(app, {})

    response = await client.get("/api/health")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_keeps_the_request_id_from_caddy(app: FastAPI, client: httpx.AsyncClient) -> None:
    use_checks(app, {})

    response = await client.get("/api/health", headers={"X-Request-ID": CADDY_REQUEST_ID})

    assert response.headers["x-request-id"] == CADDY_REQUEST_ID


@pytest.mark.parametrize("sent", ["short", "has spaces in it", "x" * 65, 'quote"and{braces}'])
async def test_replaces_a_malformed_request_id(
    app: FastAPI, client: httpx.AsyncClient, sent: str
) -> None:
    use_checks(app, {})

    response = await client.get("/api/health", headers={"X-Request-ID": sent})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_logs_written_during_a_request_carry_its_id(
    app: FastAPI, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    use_checks(app, {"valkey": refused})
    caplog.handler.addFilter(RequestIdFilter())

    with caplog.at_level(logging.WARNING, logger="app.health"):
        await client.get("/api/health", headers={"X-Request-ID": CADDY_REQUEST_ID})

    [record] = caplog.records
    assert record.__dict__["request_id"] == CADDY_REQUEST_ID

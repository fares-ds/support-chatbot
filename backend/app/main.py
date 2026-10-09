"""The FastAPI application. Every route lives under /api; Caddy serves everything else."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app import health
from app.config import Settings, get_settings
from app.request_id import RequestIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, connect_args={"timeout": 5}
        )
        valkey = Redis.from_url(settings.valkey_url, socket_connect_timeout=2)
        http = httpx.AsyncClient()
        last_beat = health.last_heartbeat(engine)
        app.state.health_checks = health.HealthChecks(
            serving={
                "postgres": health.postgres_check(engine),
                "valkey": health.valkey_check(valkey),
            },
            others={
                "tei_embed": health.http_check(http, f"{settings.tei_embed_url}/health"),
                "tei_rerank": health.http_check(http, f"{settings.tei_rerank_url}/health"),
                "ollama": health.http_check(http, f"{settings.ollama_url}/api/version"),
                # Not a serving check: live chat works while the worker is down.
                "worker": health.heartbeat_check(
                    last_beat,
                    stale_after=timedelta(seconds=settings.worker_heartbeat_stale_seconds),
                ),
            },
            schema_revision=health.schema_revision(engine),
            worker_heartbeat=last_beat,
        )
        try:
            yield
        finally:
            await http.aclose()
            await valkey.aclose()
            await engine.dispose()

    development = settings.environment == "development"
    app = FastAPI(
        title="Support Chatbot API",
        lifespan=lifespan,
        openapi_url="/api/openapi.json" if development else None,
        docs_url="/api/docs" if development else None,
        redoc_url=None,
        # Each operation is named after its route function, which the generated client's
        # functions and query options are named after in turn (ADR-0026): health, healthOptions.
        generate_unique_id_function=lambda route: route.name,
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router, prefix="/api")
    return app

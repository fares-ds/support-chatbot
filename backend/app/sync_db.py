"""Synchronous database sessions, for the worker (ADR-0024, item 8). The API uses async ones; a
worker task never wraps async code."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def sessions() -> sessionmaker[Session]:
    """Created on first use in each worker process, never before Celery forks it."""
    engine = create_engine(get_settings().sync_database_url, pool_pre_ping=True, pool_size=2)
    return sessionmaker(engine)

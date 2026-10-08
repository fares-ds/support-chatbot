"""Alembic's environment: migrates the database in SC_* settings, over the API's own driver."""

import asyncio
import logging

from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

logger = logging.getLogger("app.migrate")


def migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None)
    current = context.get_context().get_current_revision()
    if current is not None and not _known(current):
        # A newer release migrated this database, and this one is being rolled back to. Expand,
        # then contract keeps this release working on the newer schema, so leave it as it is
        # (ADR-0013); refusing would keep the rolled-back API from starting.
        logger.warning(
            "the database is at a revision this release does not know; leaving it as it is",
            extra={"revision": current},
        )
        return
    with context.begin_transaction():
        context.run_migrations()


def _known(revision: str) -> bool:
    try:
        return context.script.get_revision(revision) is not None
    except CommandError:  # Alembic's wrapping of an unknown revision
        return False


async def main() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported; migrate a database.")
asyncio.run(main())

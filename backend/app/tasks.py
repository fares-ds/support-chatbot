"""The worker's tasks."""

import logging

from celery import shared_task
from sqlalchemy import text

from app.sync_db import sessions

logger = logging.getLogger(__name__)


@shared_task(name="heartbeat")
def heartbeat() -> None:
    """Beat schedules it and the worker runs it, so a fresh beat shows both work. It reads the
    previous beat and writes this one, which the API's health report reads."""
    with sessions()() as session, session.begin():
        previous = session.execute(
            text("SELECT beat_at FROM heartbeats WHERE name = 'worker'")
        ).scalar_one_or_none()
        beat = session.execute(
            text(
                "INSERT INTO heartbeats (name, beat_at) VALUES ('worker', now())"
                " ON CONFLICT (name) DO UPDATE SET beat_at = excluded.beat_at"
                " RETURNING beat_at"
            )
        ).scalar_one()
    since = (beat - previous).total_seconds() if previous else None
    logger.info("heartbeat", extra={"since_previous_seconds": since})

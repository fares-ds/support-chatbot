"""The worker's entry point: `celery --app app.worker worker --beat` (OPS-10)."""

import logging.config
from typing import Any

from celery.signals import setup_logging, worker_ready

from app.config import get_settings
from app.jobs import create_celery
from app.logs import logging_config

settings = get_settings()
celery = create_celery(settings)


@setup_logging.connect
def _json_logs(**_: Any) -> None:
    logging.config.dictConfig(logging_config(settings.log_level))


@worker_ready.connect
def _first_beat(**_: Any) -> None:
    """Beat's first beat comes one interval after it starts. Beating now lets a fresh worker show
    as up at once."""
    celery.send_task("heartbeat")

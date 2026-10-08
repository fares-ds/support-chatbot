"""Celery's configuration: the worker and Beat run background and timed jobs, with Valkey as the
broker (OPS-10, OPS-11)."""

from datetime import timedelta

from celery import Celery

from app.config import Settings


def create_celery(settings: Settings) -> Celery:
    celery = Celery("support_chatbot", broker=settings.valkey_url, include=["app.tasks"])
    celery.conf.update(
        broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout},
        broker_connection_retry_on_startup=True,
        # A job is acknowledged once it has run, and a worker takes one at a time, so a job cut
        # short by a crash runs again after the visibility timeout. The timeout must therefore
        # stay above the longest job, or long jobs run twice (OPS-11).
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=settings.worker_concurrency,
        task_ignore_result=True,
        worker_hijack_root_logger=False,
        timezone="UTC",
        beat_schedule={
            "heartbeat": {
                "task": "heartbeat",
                "schedule": timedelta(seconds=settings.worker_heartbeat_seconds),
            },
        },
    )
    celery.loader.import_default_modules()
    return celery

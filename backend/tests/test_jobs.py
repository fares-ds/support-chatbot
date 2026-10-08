from datetime import timedelta

from app.config import Settings
from app.jobs import create_celery


def settings(**values: object) -> Settings:
    return Settings(postgres_password="test", **values)  # type: ignore[arg-type]


def test_the_broker_is_valkey_with_the_configured_visibility_timeout() -> None:
    celery = create_celery(
        settings(valkey_url="redis://valkey:6379/0", celery_visibility_timeout=7200)
    )

    assert celery.conf.broker_url == "redis://valkey:6379/0"
    assert celery.conf.broker_transport_options["visibility_timeout"] == 7200


def test_the_visibility_timeout_is_a_placeholder_until_m0_measures_the_longest_job() -> None:
    assert settings().celery_visibility_timeout == 3600


def test_beat_schedules_the_heartbeat_at_the_configured_interval() -> None:
    celery = create_celery(settings(worker_heartbeat_seconds=15))

    entry = celery.conf.beat_schedule["heartbeat"]

    assert entry["task"] == "heartbeat"
    assert entry["schedule"] == timedelta(seconds=15)
    assert "heartbeat" in celery.tasks


def test_a_job_is_acknowledged_after_it_runs_and_taken_one_at_a_time() -> None:
    """So a job cut short by a crash runs again once the visibility timeout passes (OPS-11)."""
    celery = create_celery(settings())

    assert celery.conf.task_acks_late is True
    assert celery.conf.worker_prefetch_multiplier == 1

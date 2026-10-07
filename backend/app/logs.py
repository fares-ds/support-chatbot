"""Structured logs: one JSON object per line on stdout.

Log IDs, never message or document text (SEC-10). Pass IDs through `extra`, for example
`logger.info("turn started", extra={"conversation_id": conversation.id})`.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.request_id import current_request_id

# Attributes every LogRecord has. Any other attribute came through `extra` and is logged.
# Uvicorn passes `color_message`, a duplicate of the message with terminal colours.
_RECORD_ATTRIBUTES = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            (key, value) for key, value in record.__dict__.items() if key not in _RECORD_ATTRIBUTES
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class RequestIdFilter(logging.Filter):
    """Adds the current request's ID to each record, while the record is still in its request."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = current_request_id.get()
        if request_id is not None:
            record.request_id = request_id
        return True


class HealthCheckAccessFilter(logging.Filter):
    """Drops the access line of each successful health check, which Docker runs every 10 s."""

    PATHS = frozenset({"/api/health", "/api/health/ready"})

    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access records carry (client, method, path, HTTP version, status).
        args = record.args
        return not (
            isinstance(args, tuple) and len(args) == 5 and args[2] in self.PATHS and args[4] == 200
        )


def logging_config(level: str) -> dict[str, Any]:
    """A dictConfig for the app and uvicorn alike."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter}},
        "filters": {
            "request_id": {"()": RequestIdFilter},
            "health_check_access": {"()": HealthCheckAccessFilter},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
                "filters": ["request_id"],
            },
        },
        "loggers": {"uvicorn.access": {"filters": ["health_check_access"]}},
        "root": {"level": level, "handlers": ["stdout"]},
    }

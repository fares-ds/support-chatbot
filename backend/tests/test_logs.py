import json
import logging
import sys

from app.logs import HealthCheckAccessFilter, JsonFormatter, RequestIdFilter
from app.request_id import current_request_id


def make_record(**fields: object) -> logging.LogRecord:
    base: dict[str, object] = {"name": "app.test", "levelname": "INFO", "msg": "turn started"}
    return logging.makeLogRecord(base | fields)


def format_record(record: logging.LogRecord) -> dict[str, object]:
    entry: dict[str, object] = json.loads(JsonFormatter().format(record))
    return entry


def access_record(path: str, status: int) -> logging.LogRecord:
    return make_record(
        name="uvicorn.access",
        msg='%s - "%s %s HTTP/%s" %d',
        args=("172.18.0.2:5000", "GET", path, "1.1", status),
    )


def test_formats_one_json_object_per_record() -> None:
    entry = format_record(make_record(msg="turn %s", args=("started",)))

    assert entry["level"] == "info"
    assert entry["logger"] == "app.test"
    assert entry["message"] == "turn started"
    assert isinstance(entry["time"], str)


def test_keeps_fields_passed_through_extra() -> None:
    entry = format_record(make_record(conversation_id=42))

    assert entry["conversation_id"] == 42


def test_leaves_out_uvicorns_coloured_duplicate() -> None:
    entry = format_record(make_record(color_message="\x1b[32mturn started\x1b[0m"))

    assert "color_message" not in entry


def test_includes_the_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(exc_info=sys.exc_info())

    assert "ValueError: boom" in str(format_record(record)["exception"])


def test_request_id_filter_adds_the_current_request_id() -> None:
    record = make_record()
    token = current_request_id.set("0f8fad5b-d9cb-469f-a165-70867728950e")
    try:
        RequestIdFilter().filter(record)
    finally:
        current_request_id.reset(token)

    assert format_record(record)["request_id"] == "0f8fad5b-d9cb-469f-a165-70867728950e"


def test_request_id_filter_adds_nothing_outside_a_request() -> None:
    record = make_record()

    RequestIdFilter().filter(record)

    assert "request_id" not in format_record(record)


def test_drops_successful_health_check_access_lines() -> None:
    access_filter = HealthCheckAccessFilter()

    assert not access_filter.filter(access_record("/api/health", 200))
    assert not access_filter.filter(access_record("/api/health/ready", 200))
    assert access_filter.filter(access_record("/api/health", 503))
    assert access_filter.filter(access_record("/api/conversations", 200))

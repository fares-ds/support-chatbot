"""The contract the frontend's generated client is built from (ADR-0026)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.export_contract import contract

BACKEND = Path(__file__).resolve().parents[1]


def test_the_spec_describes_the_health_endpoint_and_its_response() -> None:
    spec, _ = contract()

    response = spec["paths"]["/api/health"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FullHealthReport"
    }
    report = spec["components"]["schemas"]["FullHealthReport"]
    assert {"status", "checks", "schema_revision", "worker_heartbeat"} <= set(report["properties"])


def operation_names(spec: dict[str, Any]) -> list[str]:
    return [
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_each_operation_is_named_after_its_route_for_the_generated_client() -> None:
    spec, _ = contract()

    assert sorted(operation_names(spec)) == ["health", "ready"]


def test_no_two_operations_share_a_name() -> None:
    # The client's functions are named after them: two routes named `list` would clash. Rename
    # one of the route functions.
    names = operation_names(contract()[0])

    assert len(names) == len(set(names)), sorted(names)


def test_the_events_schema_holds_connection_ready_with_its_type_required() -> None:
    _, events = contract()

    assert events["title"] == "ServerEvent"
    assert events["oneOf"] == [{"$ref": "#/$defs/ConnectionReady"}]
    ready = events["$defs"]["ConnectionReady"]
    assert ready["properties"]["type"]["const"] == "connection.ready"
    assert set(ready["required"]) == {"type", "connected_at"}
    # Untitled fields, so the generator inlines their types rather than naming each one.
    assert all("title" not in field for field in ready["properties"].values())


def test_two_processes_write_the_same_bytes_whatever_the_shell_holds(tmp_path: Path) -> None:
    # As CI's regenerate-and-diff check does: fresh processes, different hash seeds, and the
    # second with a developer's leftover SC_ settings, which the contract must not depend on.
    leftovers = {"SC_POSTGRES_PORT": "", "SC_LOG_LEVEL": "loud", "SC_ENVIRONMENT": "development"}
    for seed, out, extra in (("1", "first", {}), ("2", "second", leftovers)):
        subprocess.run(  # noqa: S603 - this interpreter, a fixed module
            [sys.executable, "-m", "tools.export_contract", str(tmp_path / out)],
            check=True,
            cwd=BACKEND,
            env={**os.environ, "PYTHONHASHSEED": seed, **extra},
        )

    for name in ("openapi.json", "events.schema.json"):
        first = (tmp_path / "first" / name).read_bytes()
        assert first == (tmp_path / "second" / name).read_bytes()
        assert first.endswith(b"}\n")

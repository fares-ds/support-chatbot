"""Exports the contract the frontend's API client is generated from (ADR-0026), without a running
server: FastAPI's OpenAPI spec, and the WebSocket events' JSON Schema.

`python -m tools.export_contract ../frontend/api-client` writes openapi.json and
events.schema.json there. `pnpm --dir frontend generate` runs it before the generators.
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic.json_schema import models_json_schema

from app.config import Settings
from app.events import SERVER_EVENTS
from app.main import create_app


def contract() -> tuple[dict[str, Any], dict[str, Any]]:
    """The OpenAPI spec and the events' JSON Schema, as the API serves and sends them."""
    # The spec depends on no setting. model_construct takes the defaults and reads no SC_
    # variable, so a developer's shell cannot change or break the export.
    app = create_app(Settings.model_construct(postgres_password=SecretStr("unused")))
    spec = app.openapi()
    # Serialization mode: the API sends events, so a field with a default is always present.
    _, schema = models_json_schema(
        [(model, "serialization") for model in SERVER_EVENTS], title="ServerEvent"
    )
    definitions = schema["$defs"]
    for definition in definitions.values():
        # A titled field becomes its own named type in the generator, such as `Type`, which a
        # second event's `type` would clash with.
        for field in definition.get("properties", {}).values():
            field.pop("title", None)
    events = {
        "title": "ServerEvent",
        "oneOf": [{"$ref": f"#/$defs/{model.__name__}"} for model in SERVER_EVENTS],
        "$defs": definitions,
    }
    return spec, events


def write_contract(directory: Path) -> None:
    spec, events = contract()
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in (("openapi.json", spec), ("events.schema.json", events)):
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        (directory / name).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tools.export_contract OUT_DIR")
    write_contract(Path(sys.argv[1]))

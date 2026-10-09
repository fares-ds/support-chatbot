"""The events the API sends over WebSockets (RT-1 to RT-8). Each one is a Pydantic model with a
literal `type`; the dashboard and the widget get their TypeScript types from these models' JSON
Schema (ADR-0026). M1 adds the conversation events beside the first.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ServerEvent(BaseModel):
    """What every event shares. The API always sends a field with a default, so its schema
    lists it as required, and clients may rely on it."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ConnectionReady(ServerEvent):
    """Sent once a WebSocket connects. A client that reconnected then fetches the messages after
    the last sequence it holds, and takes live events from here on (RT-5)."""

    type: Literal["connection.ready"] = "connection.ready"
    connected_at: datetime


SERVER_EVENTS: tuple[type[ServerEvent], ...] = (ConnectionReady,)
"""Every event the API sends, in the order their types are generated."""

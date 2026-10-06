"""Request IDs: one per request, carried in the logs and in the X-Request-ID response header."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "x-request-id"

# Caddy sends a UUID. Anything else is replaced, so a client cannot write into the logs.
_VALID = re.compile(r"[A-Za-z0-9-]{8,64}")

current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


class RequestIdMiddleware:
    """Takes the request ID that Caddy sets, or makes one, and returns it with the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = current_request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            current_request_id.reset(token)


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == HEADER.encode():
            candidate: str = value.decode("latin-1")
            return candidate if _VALID.fullmatch(candidate) else None
    return None

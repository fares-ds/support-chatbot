"""Runs the API: `python -m app`."""

import uvicorn

from app.config import get_settings
from app.logs import logging_config


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        # All interfaces inside the container. Its port is not published; only Caddy reaches it.
        host="0.0.0.0",  # noqa: S104
        port=8000,
        log_config=logging_config(settings.log_level),
        proxy_headers=True,
        forwarded_allow_ips="*",
        server_header=False,
    )


if __name__ == "__main__":
    main()

"""The worker container's health check: exits 0 when this worker answers a ping through Valkey,
1 otherwise, such as when Valkey cannot be reached."""

import socket
import sys

from app.worker import celery


def main() -> int:
    try:
        with celery.connection_for_write() as connection:
            connection.ensure_connection(max_retries=1, timeout=3)
            replies = celery.control.ping(
                destination=[f"celery@{socket.gethostname()}"], timeout=5, connection=connection
            )
    except Exception:  # Valkey refused or timed out
        return 1
    return 0 if replies else 1


if __name__ == "__main__":
    sys.exit(main())

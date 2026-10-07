"""The container's health check: exits 0 when the API reports healthy, 1 otherwise.

Standard library only, so the check stays cheap when Docker runs it every 10 seconds.
"""

import sys
import urllib.request

URL = "http://127.0.0.1:8000/api/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=4) as response:
            return 0 if response.status == 200 else 1
    except OSError:  # refused, timed out, or an HTTP error status such as 503
        return 1


if __name__ == "__main__":
    sys.exit(main())

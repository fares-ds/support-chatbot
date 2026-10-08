"""The migration job: `python -m app.migrate` upgrades the database to the newest revision.

It runs once per upgrade in a one-off container, before the API and the worker start, and never
on their startup (ADR-0013, OPS-3). Running it again changes nothing.
"""

import logging
import logging.config
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.logs import logging_config

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

logger = logging.getLogger("app.migrate")  # __name__ is "__main__" under python -m


def main() -> None:
    logging.config.dictConfig(logging_config(get_settings().log_level))
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    logger.info("migrating the database to the newest revision")
    command.upgrade(config, "head")
    logger.info("the migration job finished")


if __name__ == "__main__":
    main()

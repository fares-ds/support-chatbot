"""Add the heartbeats table

Revision 0002, created 2026-10-08.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Expand, then contract (ADR-0013): add tables, nullable columns and indexes, so the previous
# release keeps working on the new schema. Dropping or renaming a table or column is the contract
# step for something the previous release had already stopped using, and says what, for CI:
# contract = "Release 1.4 stopped reading users.legacy_name"


def upgrade() -> None:
    # One row per heartbeat: the worker writes "worker" on every beat (OPS-7, OPS-10).
    op.create_table(
        "heartbeats",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """No downgrades: a rollback restores the pre-upgrade backup (ADR-0013)."""
    pass

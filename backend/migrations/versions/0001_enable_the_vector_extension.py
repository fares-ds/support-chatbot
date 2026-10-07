"""Enable the vector extension

Revision 0001, created 2026-10-07.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Expand, then contract (ADR-0013): add tables, nullable columns and indexes, so the previous
# release keeps working on the new schema. Dropping or renaming a table or column is the contract
# step for something the previous release had already stopped using, and says what, for CI:
# contract = "Release 1.4 stopped reading users.legacy_name"


def upgrade() -> None:
    # pgvector, for chunk embeddings stored as halfvec (KB-7).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """No downgrades: a rollback restores the pre-upgrade backup (ADR-0013)."""
    pass

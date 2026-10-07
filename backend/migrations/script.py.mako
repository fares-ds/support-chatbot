"""${message}

Revision ${up_revision}, created ${create_date.strftime("%Y-%m-%d")}.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}

# Expand, then contract (ADR-0013): add tables, nullable columns and indexes, so the previous
# release keeps working on the new schema. Dropping or renaming a table or column is the contract
# step for something the previous release had already stopped using, and says what, for CI:
# contract = "Release 1.4 stopped reading users.legacy_name"


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """No downgrades: a rollback restores the pre-upgrade backup (ADR-0013)."""
    pass

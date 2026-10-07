from pathlib import Path
from textwrap import dedent

import pytest

from tools.migration_rules import check_directory, problems


def migration(upgrade: str, downgrade: str = "pass", header: str = "") -> str:
    return dedent(f'''
        """A migration."""
        import sqlalchemy as sa
        from alembic import op

        revision = "0002"
        down_revision = "0001"
        {header}

        def upgrade() -> None:
            {upgrade}


        def downgrade() -> None:
            {downgrade}
    ''')


def test_dropping_a_column_is_refused() -> None:
    found = problems(migration('op.drop_column("users", "legacy_name")'))

    assert len(found) == 1
    assert "drop_column" in found[0]


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.drop_table("users")',
        'op.rename_table("users", "people")',
        'op.alter_column("users", "name", new_column_name="full_name")',
        'with op.batch_alter_table("users") as batch:\n                batch.drop_column("name")',
        'op.execute("ALTER TABLE users DROP COLUMN name")',
        'op.execute("drop table users")',
        'op.execute(sa.text("ALTER TABLE users RENAME COLUMN name TO full_name"))',
        'op.execute("ALTER TABLE users RENAME TO people")',
    ],
)
def test_every_way_to_drop_or_rename_is_refused(upgrade: str) -> None:
    assert len(problems(migration(upgrade))) == 1


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True))',
        'op.add_column("users", sa.Column("nickname", sa.Text()))',
        'op.create_index("users_name", "users", ["name"])',
        'op.drop_index("users_old_name")',
        'op.execute("CREATE EXTENSION IF NOT EXISTS vector")',
    ],
)
def test_adding_is_allowed(upgrade: str) -> None:
    assert problems(migration(upgrade)) == []


def test_the_contract_step_may_drop_what_the_previous_release_stopped_using() -> None:
    marked = 'contract = "Release 1.3 stopped reading users.legacy_name"'

    assert problems(migration('op.drop_column("users", "legacy_name")', header=marked)) == []


def test_a_contract_step_must_say_what_it_removes() -> None:
    found = problems(migration('op.drop_column("users", "legacy_name")', header='contract = ""'))

    assert len(found) == 1


@pytest.mark.parametrize(
    "downgrade",
    [
        'op.drop_table("users")',
        'raise NotImplementedError("no downgrades")',
        'op.execute("SELECT 1")',
    ],
)
def test_a_downgrade_that_does_anything_is_refused(downgrade: str) -> None:
    found = problems(migration('op.create_table("users")', downgrade=downgrade))

    assert len(found) == 1
    assert "downgrade" in found[0]


def test_a_downgrade_may_explain_why_it_does_nothing() -> None:
    downgrade = (
        '"""No downgrades: restore the pre-upgrade backup instead (ADR-0013)."""\n            pass'
    )

    assert problems(migration('op.create_table("users")', downgrade=downgrade)) == []


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.add_column("users", sa.Column("age", sa.Integer(), nullable=False))',
        'with op.batch_alter_table("users") as batch:\n'
        '                batch.add_column(sa.Column("age", sa.Integer(), nullable=False))',
    ],
)
def test_a_not_null_column_without_a_server_default_is_refused(upgrade: str) -> None:
    found = problems(migration(upgrade))

    assert len(found) == 1
    assert "server_default" in found[0]


@pytest.mark.parametrize(
    "upgrade",
    [
        'op.add_column("users", sa.Column("age", sa.Integer(), nullable=False,'
        ' server_default="0"))',
        'op.create_table("pets", sa.Column("name", sa.Text(), nullable=False))',
    ],
)
def test_a_not_null_column_is_allowed_with_a_server_default_or_in_a_new_table(
    upgrade: str,
) -> None:
    assert problems(migration(upgrade)) == []


def test_a_directory_check_names_each_file_with_a_problem(tmp_path: Path) -> None:
    (tmp_path / "0001_users.py").write_text(migration('op.create_table("users")'))
    (tmp_path / "0002_drop.py").write_text(migration('op.drop_table("users")'))
    (tmp_path / "__init__.py").write_text("")

    found = check_directory(tmp_path)

    assert [line.split(":")[0] for line in found] == ["0002_drop.py"]

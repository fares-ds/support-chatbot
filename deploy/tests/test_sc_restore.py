import stat
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeHost, installed, sc


def yes(question: str) -> bool:
    return True


def restore(host: FakeHost, opt: Path, snapshot: str = "latest") -> int:
    """sc restore, confirmed, with short pauses between health checks."""
    return sc.restore(
        host, install_dir=opt, snapshot=snapshot, confirm=yes, health_timeout=0.5, retry_every=0.01
    )


def lost_server(tmp_path: Path) -> FakeHost:
    """A server whose last backup outlived it, in its off-server repository."""
    old = FakeHost(
        database=b"PGDMP a month of conversations",
        files={"kb/refunds.pdf": b"%PDF refunds", "parsed/refunds.md": b"# Refunds"},
    )
    assert sc.backup(old, install_dir=installed(tmp_path / "old")) == 0
    return old


def fresh_install(old: FakeHost) -> FakeHost:
    return FakeHost(database=b"PGDMP empty", files={}, repository=old.repository)


def steps(host: FakeHost) -> list[str]:
    """What sc did, named by the program it ran."""
    named = []
    for ran in host.ran:
        if "restic" in ran.args:
            named.append(f"restic {ran.args[ran.args.index('restic') + 1]}")
        elif ran.args[:3] == ["docker", "compose", "exec"]:
            named.append(ran.args[5])
        else:
            named.append(" ".join(ran.args[:4]))
    return named


def test_a_restore_onto_a_fresh_install_brings_back_the_database_and_the_files(
    tmp_path: Path,
) -> None:
    old = lost_server(tmp_path)
    new = fresh_install(old)
    # The vendor pasted the old install's key and repository settings into the new .env.
    opt = installed(tmp_path / "new")

    assert restore(new, opt) == 0

    assert new.database == old.database
    assert new.files == old.files
    assert steps(new) == [
        "restic snapshots",
        "restic dump",  # the key's fingerprint
        "restic dump",  # the database
        "docker compose stop api",
        "valkey-cli",
        "restic restore",
        "dropdb",
        "createdb",
        "pg_restore",
        "docker compose run --rm",
        "docker compose up --detach",
        "fetch https://chat.example.com/api/health",
    ]
    assert not (opt / "backup" / "support_chatbot.dump").exists()


def test_a_restore_with_another_key_in_env_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = fresh_install(lost_server(tmp_path))
    # The vendor forgot to paste the old key: .env holds the one sc install generated.
    opt = installed(tmp_path / "new", SC_ENCRYPTION_KEY="bmV3LWtleS1mcm9tLXNjLWluc3RhbGw=")

    assert restore(new, opt) == 1

    assert steps(new) == ["restic snapshots", "restic dump"]
    assert new.database == b"PGDMP empty"
    error = capsys.readouterr().err
    assert "different SC_ENCRYPTION_KEY" in error
    assert "Nothing was changed." in error


def test_a_restore_the_vendor_does_not_confirm_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = fresh_install(lost_server(tmp_path))
    asked = []

    def no(question: str) -> bool:
        asked.append(question)
        return False

    assert (
        sc.restore(new, install_dir=installed(tmp_path / "new"), snapshot="latest", confirm=no) == 1
    )

    assert "replaces" in asked[0] and "chat.example.com" in asked[0]
    assert steps(new) == ["restic snapshots", "restic dump"]
    assert "Nothing was changed." in capsys.readouterr().err


def test_a_restore_restores_the_snapshot_it_asked_about_even_if_a_backup_lands_meanwhile(
    tmp_path: Path,
) -> None:
    old = lost_server(tmp_path)
    [asked_about] = old.repository.snapshots
    new = fresh_install(old)

    def a_backup_lands(question: str) -> bool:
        assert f"snapshot {asked_about.id[:8]} from {asked_about.time}" in question
        old.database = b"PGDMP a later day"
        assert sc.backup(old, install_dir=tmp_path / "old" / "opt") == 0
        return True

    assert (
        sc.restore(
            new,
            install_dir=installed(tmp_path / "new"),
            snapshot="latest",
            confirm=a_backup_lands,
            health_timeout=0.5,
            retry_every=0.01,
        )
        == 0
    )

    assert new.database == b"PGDMP a month of conversations"


def test_a_snapshot_that_does_not_exist_is_named_and_nothing_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = fresh_install(lost_server(tmp_path))

    assert restore(new, installed(tmp_path / "new"), snapshot="0badc0de") == 1

    assert steps(new) == ["restic snapshots"]
    error = capsys.readouterr().err
    assert "No snapshot 0badc0de in the repository" in error
    assert "Nothing was changed." in error


def test_an_unreachable_repository_is_reported_before_anything_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = fresh_install(lost_server(tmp_path))
    new.fail_times = {"docker compose run": 1}

    assert restore(new, installed(tmp_path / "new")) == 1

    error = capsys.readouterr().err
    assert "Reading the repository failed" in error
    assert "Nothing was changed." in error
    assert new.database == b"PGDMP empty"


@pytest.mark.parametrize(
    ("failing", "named"),
    [
        ("docker compose stop", "Stopping the API and the worker"),
        ("docker compose exec", "Emptying the job queue"),
        ("docker compose up", "Starting the stack"),
    ],
)
def test_a_restore_that_stops_midway_names_the_step_and_can_run_again(
    failing: str, named: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = lost_server(tmp_path)
    new = fresh_install(old)
    new.fail_times = {failing: 1}
    opt = installed(tmp_path / "new")

    assert restore(new, opt) == 1
    error = capsys.readouterr().err
    assert f"The restore stopped while {named[0].lower()}{named[1:]}" in error
    assert "run sc restore again" in error

    assert restore(new, opt) == 0
    assert new.database == old.database
    dropped = [ran.args for ran in new.ran if "dropdb" in ran.args]
    assert all("--if-exists" in args for args in dropped)


def test_a_restore_with_no_repository_set_says_what_to_paste(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert restore(host, installed(tmp_path, SC_RESTIC_REPOSITORY="")) == 1

    assert "No backup repository is set: add SC_RESTIC_REPOSITORY" in capsys.readouterr().err
    assert host.ran == []


@pytest.mark.parametrize(("typed", "confirmed"), [("yes", True), ("y", False), ("", False)])
def test_only_a_typed_yes_confirms_a_restore(
    typed: str, confirmed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: typed)

    assert sc.ask_yes("Continue?") is confirmed


def test_no_answer_at_all_does_not_confirm_a_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    def closed(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)

    assert sc.ask_yes("Continue?") is False


def test_no_backup_starts_while_a_restore_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = fresh_install(lost_server(tmp_path))
    opt = installed(tmp_path / "new")
    meanwhile: list[int] = []

    def cron_fires(question: str) -> bool:
        meanwhile.append(sc.backup(FakeHost(), install_dir=opt))
        return True

    assert (
        sc.restore(
            new,
            install_dir=opt,
            snapshot="latest",
            confirm=cron_fires,
            health_timeout=0.5,
            retry_every=0.01,
        )
        == 0
    )

    assert meanwhile == [1]
    assert "Another backup or restore is running" in capsys.readouterr().err


def test_after_a_restore_the_backup_directory_still_belongs_to_this_servers_account(
    tmp_path: Path,
) -> None:
    new = fresh_install(lost_server(tmp_path))
    opt = installed(tmp_path / "new")

    assert restore(new, opt) == 0

    # Otherwise the next cron backup, as this server's service account, could not write there.
    assert new.owners[opt / "backup"] == "supportchatbot"


def test_a_restore_as_the_service_account_makes_backup_before_docker_would(
    tmp_path: Path,
) -> None:
    old = lost_server(tmp_path)
    new = FakeHost(root=False, database=b"PGDMP empty", files={}, repository=old.repository)
    opt = installed(tmp_path / "new")  # no backup has run here, so there is no backup/ yet

    assert restore(new, opt) == 0

    assert new.owners.get(opt / "backup") != "root"
    assert stat.S_IMODE((opt / "backup").stat().st_mode) == 0o700


def test_a_full_disk_while_fetching_the_dump_is_a_plain_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = lost_server(tmp_path)

    class FullDisk(FakeHost):
        def run(self, args: list[str], **kwargs: Any) -> str:
            if "dump" in args and kwargs.get("stdout_to"):
                raise OSError(28, "No space left on device")
            return super().run(args, **kwargs)

    new = FullDisk(database=b"PGDMP empty", files={}, repository=old.repository)

    assert restore(new, installed(tmp_path / "new")) == 1

    assert "The restore stopped while fetching the database dump" in capsys.readouterr().err
    assert new.database == b"PGDMP empty"


def test_a_restore_in_place_drops_the_jobs_queued_after_the_snapshot(tmp_path: Path) -> None:
    host = lost_server(tmp_path)
    host.queue = ["ingest a document uploaded after the snapshot"]

    assert restore(host, tmp_path / "old" / "opt") == 0

    assert host.queue == []

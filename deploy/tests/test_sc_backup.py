import json
from pathlib import Path
from typing import Any

import pytest
from conftest import DEPLOY, KEY, RESTIC_PASSWORD, FakeHost, FakeRepository, installed, sc


def status(opt: Path) -> dict[str, object]:
    result: dict[str, object] = json.loads((opt / "backup-status.json").read_text())
    return result


def test_a_backup_snapshots_the_database_and_the_files_and_records_its_time(
    host: FakeHost, tmp_path: Path
) -> None:
    opt = installed(tmp_path)

    assert sc.backup(host, install_dir=opt) == 0

    [snapshot] = host.repository.snapshots
    assert snapshot.paths == ["/backup/database", "/data/files"]
    assert snapshot.staged["support_chatbot.dump"] == host.database
    assert snapshot.stored == host.files
    assert snapshot.host == "chat.example.com"
    recorded = status(opt)
    assert recorded["last_run"] == {
        "at": recorded["last_success"],
        "ok": True,
        "snapshot": snapshot.id,
        "message": f"Snapshot {snapshot.id[:8]} saved.",
    }
    assert not (opt / "backup" / "support_chatbot.dump").exists()


def test_the_first_backup_creates_the_repository(tmp_path: Path) -> None:
    host = FakeHost(repository=FakeRepository(exists=False))

    assert sc.backup(host, install_dir=installed(tmp_path)) == 0

    assert host.repository.exists
    assert len(host.repository.snapshots) == 1


def test_a_backup_with_no_repository_set_fails_plainly_and_is_recorded(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path, SC_RESTIC_REPOSITORY="")

    assert sc.backup(host, install_dir=opt) == 1

    assert "No backup repository is set: add SC_RESTIC_REPOSITORY" in capsys.readouterr().err
    assert status(opt)["last_run"]["ok"] is False  # type: ignore[index]
    assert status(opt)["last_success"] is None
    assert host.ran == []


@pytest.mark.parametrize(
    ("failing", "named"),
    [
        ("docker compose exec", "Dumping the database failed"),
        ("docker compose run", "Saving the snapshot to the repository failed"),
    ],
)
def test_a_failed_backup_says_which_step_failed_and_keeps_the_last_success(
    failing: str, named: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path)
    assert sc.backup(FakeHost(), install_dir=opt) == 0
    succeeded = status(opt)["last_success"]

    assert sc.backup(FakeHost(fail_times={failing: 1}), install_dir=opt) == 1

    assert named in capsys.readouterr().err
    recorded = status(opt)
    assert recorded["last_run"]["ok"] is False  # type: ignore[index]
    assert named in recorded["last_run"]["message"]  # type: ignore[index]
    assert recorded["last_success"] == succeeded
    assert not (opt / "backup" / "support_chatbot.dump").exists()


def test_with_sudo_it_runs_as_the_service_account_so_the_cron_job_can_follow(
    tmp_path: Path,
) -> None:
    opt = installed(tmp_path)
    host = FakeHost(root=True)

    assert sc.backup(host, install_dir=opt) == 0

    assert {ran.user for ran in host.ran} == {"supportchatbot"}
    assert host.owners[opt / "backup"] == "supportchatbot"
    assert host.owners[opt / "backup-status.json"] == "supportchatbot"


def test_the_cron_job_runs_it_as_the_service_account_itself(tmp_path: Path) -> None:
    host = FakeHost(root=False)

    assert sc.backup(host, install_dir=installed(tmp_path)) == 0

    assert {ran.user for ran in host.ran} == {None}


def restic_runs(host: FakeHost) -> list[list[str]]:
    return [ran.args for ran in host.ran if ran.args[:3] == ["docker", "compose", "run"]]


def test_a_repository_on_a_local_path_is_mounted_into_restics_container(
    host: FakeHost, tmp_path: Path
) -> None:
    opt = installed(tmp_path, SC_RESTIC_REPOSITORY="/mnt/backups/acme")

    assert sc.backup(host, install_dir=opt) == 0

    for args in restic_runs(host):
        assert args[args.index("--volume") + 1] == "/mnt/backups/acme:/mnt/backups/acme"


def test_a_remote_repository_is_not_mounted(host: FakeHost, tmp_path: Path) -> None:
    assert sc.backup(host, install_dir=installed(tmp_path)) == 0

    assert all("--volume" not in args for args in restic_runs(host))


def test_no_secret_reaches_the_snapshot_the_arguments_or_the_output(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aws_secret = "aws" + "s" * 37
    opt = installed(tmp_path, SC_RESTIC_AWS_SECRET_ACCESS_KEY=aws_secret)

    assert sc.backup(host, install_dir=opt) == 0

    # The key stays with the vendor, out of the backup (ADR-0033).
    [snapshot] = host.repository.snapshots
    output = capsys.readouterr()
    for secret in (KEY, RESTIC_PASSWORD, "p" * 64, aws_secret):
        assert all(secret.encode() not in content for content in snapshot.staged.values())
        assert all(secret not in " ".join(ran.args) for ran in host.ran)
        assert secret not in output.out + output.err + (opt / "backup-status.json").read_text()


def test_a_server_without_an_install_is_named(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sc.backup(host, install_dir=tmp_path / "opt") == 1

    assert f"Support Chatbot is not installed in {tmp_path / 'opt'}" in capsys.readouterr().err
    assert host.ran == []


def test_a_user_who_cannot_read_env_is_told_who_can(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path)
    (opt / ".env").chmod(0o000)
    host = FakeHost(root=False)

    try:
        assert sc.backup(host, install_dir=opt) == 1
    finally:
        (opt / ".env").chmod(0o600)

    assert "Run sc backup with sudo, or as supportchatbot." in capsys.readouterr().err
    assert host.ran == []


def test_a_dump_that_is_not_a_pg_dump_archive_fails_the_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Say a login script on the server printed a greeting into the dump's stream.
    host = FakeHost(database=b"Welcome to Ubuntu 24.04\nPGDMP the database")

    assert sc.backup(host, install_dir=installed(tmp_path)) == 1

    assert "Dumping the database failed" in capsys.readouterr().err
    assert host.repository.snapshots == []


def test_a_backup_refuses_to_start_while_another_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path)
    meanwhile: list[int] = []

    class CronFiresMidway(FakeHost):
        def run(self, args: list[str], **kwargs: Any) -> str:
            if "pg_dump" in args and not meanwhile:
                meanwhile.append(sc.backup(FakeHost(), install_dir=opt))
            return super().run(args, **kwargs)

    assert sc.backup(CronFiresMidway(), install_dir=opt) == 0

    assert meanwhile == [1]
    assert "Another backup or restore is running" in capsys.readouterr().err
    assert status(opt)["last_run"]["ok"] is True  # type: ignore[index]


@pytest.mark.parametrize(
    "repository",
    [
        "backups",  # relative: restic would write it inside its throwaway container
        "local:backups",
        "sftp:backup@host:/srv/restic",  # needs keys the container does not have
        "b2:bucket:/acme",  # needs credentials sc does not pass
    ],
)
def test_a_repository_sc_cannot_reach_is_refused_before_anything_runs(
    repository: str, host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path, SC_RESTIC_REPOSITORY=repository)

    assert sc.backup(host, install_dir=opt) == 1

    assert "SC_RESTIC_REPOSITORY" in capsys.readouterr().err
    assert host.ran == []
    assert status(opt)["last_run"]["ok"] is False  # type: ignore[index]


@pytest.mark.parametrize(
    "repository",
    ["s3:https://s3.example.com/b/acme", "rest:https://u:p@backup.example.com/acme", "/mnt/b"],
)
def test_s3_rest_and_absolute_paths_are_accepted(
    repository: str, host: FakeHost, tmp_path: Path
) -> None:
    assert sc.backup(host, install_dir=installed(tmp_path, SC_RESTIC_REPOSITORY=repository)) == 0


def test_a_full_disk_while_dumping_is_recorded_as_a_failed_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed(tmp_path)
    assert sc.backup(FakeHost(), install_dir=opt) == 0

    class FullDisk(FakeHost):
        def run(self, args: list[str], **kwargs: Any) -> str:
            if "pg_dump" in args:
                raise OSError(28, "No space left on device")
            return super().run(args, **kwargs)

    assert sc.backup(FullDisk(), install_dir=opt) == 1

    assert "Dumping the database failed: [Errno 28] No space left" in capsys.readouterr().err
    assert status(opt)["last_run"]["ok"] is False  # type: ignore[index]


def test_the_bundle_mounts_what_sc_backs_up_where_sc_expects_it() -> None:
    compose = (DEPLOY / "compose.yaml").read_text()

    def service(name: str) -> str:
        start = compose.index(f"\n  {name}:\n")
        return compose[start : compose.index("\n\n", start)]

    assert f"- ./backup:{sc.STAGED}\n" in service("restic")
    for name in ("restic", "api", "worker"):
        assert f"- files:{sc.FILES}\n" in service(name), name

from pathlib import Path
from typing import Any

import pytest
from conftest import FakeHost, installed, sc


def compose(version: str) -> str:
    image = f"ghcr.io/fares-ds/support-chatbot-backend:{version}"
    return f"name: support-chatbot\nservices:\n  api:\n    image: {image}\n"


def installed_release(tmp_path: Path, version: str = "1.4.0") -> Path:
    """An install of `version`, as sc install leaves it, with a backup repository set."""
    opt = installed(tmp_path)
    (opt / ".installed").write_text(f"version={version}\ninstalled=2026-09-01T03:00:00+0000\n")
    (opt / "compose.yaml").write_text(compose(version))
    for name in ("Caddyfile", "env.template", "sc", "README.md"):
        (opt / name).write_text(f"# {name} of {version}\n")
    return opt


def release_bundle(tmp_path: Path, version: str = "1.5.0", upgrades_from: str = "1.4.0") -> Path:
    """An unpacked release bundle, as build_bundle.py makes it."""
    bundle = tmp_path / f"support-chatbot-{version}"
    bundle.mkdir()
    (bundle / "compose.yaml").write_text(compose(version))
    (bundle / "release.txt").write_text(f"version={version}\nupgrades_from={upgrades_from}\n")
    (bundle / "env.template").write_text(
        "SC_DOMAIN=\nSC_POSTGRES_PASSWORD=\nSC_ENCRYPTION_KEY=\nSC_RESTIC_PASSWORD=\n"
    )
    for name in ("Caddyfile", "sc", "README.md"):
        (bundle / name).write_text(f"# {name} of {version}\n")
    return bundle


def upgrade(host: FakeHost, opt: Path, bundle: Path, target: str = "1.5.0") -> int:
    """sc upgrade, with short pauses between health checks."""
    return sc.upgrade(
        host, bundle=bundle, install_dir=opt, target=target, health_timeout=0.5, retry_every=0.01
    )


def step(host: FakeHost, words: str) -> int:
    """Where in the run a command starting with `words` first ran."""
    return next(i for i, ran in enumerate(host.ran) if " ".join(ran.args).startswith(words))


def test_an_upgrade_backs_up_then_migrates_and_leaves_the_new_release_running(
    tmp_path: Path,
) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0")
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 0

    assert host.running == "1.5.0" and host.schema == "1.5.0"
    assert "version=1.5.0" in (opt / ".installed").read_text()
    assert "backend:1.5.0" in (opt / "compose.yaml").read_text()
    assert "backend:1.4.0" in (opt / "previous" / "compose.yaml").read_text()
    [snapshot] = host.repository.snapshots
    assert {"pre-upgrade", "from-1.4.0", "to-1.5.0"} <= set(snapshot.tags)
    # Backed up and pulled before anything stopped; migrated once before starting.
    order = [
        step(host, "docker compose run --rm -T restic backup"),
        step(host, "docker compose --project-directory . --file next/compose.yaml"),
        step(host, "docker compose stop api worker"),
        step(host, "docker compose run --rm migrate"),
        step(host, "docker compose up --detach --wait"),
    ]
    assert order == sorted(order)
    assert not (opt / "next").exists()


@pytest.mark.parametrize("installed_version", ["0.2.0", "0.2.5", "0.10.0"])
def test_a_release_upgrades_from_the_release_ci_tested_or_later(installed_version: str) -> None:
    assert sc.upgrade_problem(installed_version, "0.11.0", upgrades_from="0.2.0") is None


@pytest.mark.parametrize(
    ("installed_version", "target", "upgrades_from", "named"),
    [
        ("0.1.0", "0.3.0", "0.2.0", "upgrade to 0.2.0 first"),  # a skipped release
        ("0.3.0", "0.3.0", "0.2.0", "already"),
        ("0.4.0", "0.3.0", "0.2.0", "older"),
        ("0.1.0", "0.2.0", "", "first release"),  # nothing to upgrade from
    ],
)
def test_any_other_path_is_refused_with_the_reason(
    installed_version: str, target: str, upgrades_from: str, named: str
) -> None:
    problem = sc.upgrade_problem(installed_version, target, upgrades_from=upgrades_from)

    assert problem is not None and named in problem


@pytest.mark.parametrize(
    ("host", "installed_version", "target", "named"),
    [
        (FakeHost(running="1.4.0"), "1.4.0", "1.6.0", "This bundle is 1.5.0, not 1.6.0"),
        (FakeHost(running="1.3.0"), "1.3.0", "1.5.0", "upgrade to 1.4.0 first"),
        (FakeHost(running="1.4.0", free_gb=5), "1.4.0", "1.5.0", "free space"),
        (FakeHost(running="1.4.0", root=False), "1.4.0", "1.5.0", "sudo"),
        (FakeHost(running="1.4.0", unhealthy={"1.4.0"}), "1.4.0", "1.5.0", "not healthy"),
    ],
)
def test_an_upgrade_that_cannot_start_says_why_and_changes_nothing(
    host: FakeHost,
    installed_version: str,
    target: str,
    named: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opt = installed_release(tmp_path, installed_version)

    assert upgrade(host, opt, release_bundle(tmp_path), target) == 1

    error = capsys.readouterr().err
    assert named in error and "Nothing was changed." in error
    assert host.repository.snapshots == []
    assert f"backend:{installed_version}" in (opt / "compose.yaml").read_text()
    assert not any("pull" in ran.args or "stop" in ran.args for ran in host.ran)


@pytest.mark.parametrize(
    ("break_it", "named"),
    [
        ("no repository", "the backup failed"),
        ("pull fails", "Pulling 1.5.0's images failed"),
    ],
)
def test_a_failed_backup_or_pull_stops_the_upgrade_before_the_install_changes(
    break_it: str, named: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0")
    opt = installed_release(tmp_path)
    if break_it == "no repository":
        env = (
            (opt / ".env").read_text().replace("SC_RESTIC_REPOSITORY=s3:", "SC_RESTIC_REPOSITORY=#")
        )
        (opt / ".env").write_text(env)
    else:
        host.fail_times = {"docker compose --project-directory": 1}

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    error = capsys.readouterr().err
    assert named in error and "Nothing was changed" in error
    assert host.running == "1.4.0" and host.schema == "1.4.0"
    assert "backend:1.4.0" in (opt / "compose.yaml").read_text()
    assert "version=1.4.0" in (opt / ".installed").read_text()
    assert not (opt / "next").exists() and not (opt / "previous").exists()
    assert not any("stop" in ran.args for ran in host.ran)


@pytest.mark.parametrize(
    ("host", "while_"),
    [
        (FakeHost(running="1.4.0", schema="1.4.0", failing_migrations={"1.5.0"}), "migrating"),
        (FakeHost(running="1.4.0", schema="1.4.0", unhealthy={"1.5.0"}), "checking"),
    ],
)
def test_a_failed_upgrade_puts_the_previous_release_back(
    host: FakeHost, while_: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    assert host.running == "1.4.0"
    assert "backend:1.4.0" in (opt / "compose.yaml").read_text()
    assert "version=1.4.0" in (opt / ".installed").read_text()
    [snapshot] = host.repository.snapshots
    error = capsys.readouterr().err
    assert f"The upgrade to 1.5.0 failed while {while_}" in error
    assert "Rolled back: 1.4.0 runs again" in error
    assert f"snapshot {snapshot.id[:8]}" in error


def test_a_previous_release_that_cannot_run_on_the_new_schema_gets_the_backup_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 1.5.0's migration breaks 1.4.0, then 1.5.0 never turns healthy.
    host = FakeHost(running="1.4.0", schema="1.4.0", breaking={"1.5.0"}, unhealthy={"1.5.0"})
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    [snapshot] = host.repository.snapshots
    assert any(
        ran.args[-2:] == [snapshot.id, "/backup/database/support_chatbot.dump"] for ran in host.ran
    )
    assert any("pg_restore" in ran.args for ran in host.ran)
    assert host.running == "1.4.0" and host.schema == "1.4.0"
    assert "version=1.4.0" in (opt / ".installed").read_text()
    error = capsys.readouterr().err
    assert "1.4.0 cannot run on the migrated database" in error
    assert f"Rolled back: 1.4.0 runs again, with the data as of snapshot {snapshot.id[:8]}" in error


def test_a_rollback_that_fails_too_says_what_to_do_by_hand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class RepositoryGone(FakeHost):
        """The repository answers the pre-upgrade backup, then not the restore."""

        def run(self, args: list[str], **kwargs: Any) -> str:
            if "restic" in args and "snapshots" in args:
                raise sc.CommandFailed(args, "Fatal: unable to open repository")
            return super().run(args, **kwargs)

    host = RepositoryGone(running="1.4.0", schema="1.4.0", breaking={"1.5.0"}, unhealthy={"1.5.0"})
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    [snapshot] = host.repository.snapshots
    error = capsys.readouterr().err
    assert "The rollback failed too" in error
    assert f"sc restore --snapshot {snapshot.id[:8]}" in error


def test_an_upgrade_keeps_the_secrets_and_adds_any_the_new_release_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Say the new release generates a secret the installed one did not.
    monkeypatch.setitem(sc.GENERATED, "SC_SESSION_KEY", lambda: "s" * 64)
    host = FakeHost(running="1.4.0", schema="1.4.0")
    opt = installed_release(tmp_path)
    before = (opt / ".env").read_text()

    assert upgrade(host, opt, release_bundle(tmp_path)) == 0

    after = (opt / ".env").read_text()
    assert all(line in after.splitlines() for line in before.splitlines())
    assert "SC_SESSION_KEY=" + "s" * 64 in after
    output = capsys.readouterr()
    secrets = [
        line.split("=", 1)[1]
        for line in after.splitlines()
        if "KEY=" in line or "PASSWORD=" in line
    ]
    for secret in secrets:
        assert secret not in output.out + output.err
        assert all(secret not in " ".join(ran.args) for ran in host.ran)


def test_a_new_worker_that_never_beats_fails_even_after_the_old_one_beat_as_it_stopped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0", silent={"1.5.0"})
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    assert host.running == "1.4.0"
    assert "failed while checking the new release's health" in capsys.readouterr().err


def test_a_cron_backup_refused_during_the_upgrade_does_not_lose_the_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = installed_release(tmp_path)

    class CronFiresDuringThePull(FakeHost):
        def run(self, args: list[str], **kwargs: Any) -> str:
            if "pull" in args:  # the daily backup, while the upgrade holds the lock
                assert sc.backup(FakeHost(root=False), install_dir=opt) == 1
            return super().run(args, **kwargs)

    host = CronFiresDuringThePull(running="1.4.0", schema="1.4.0", failing_migrations={"1.5.0"})

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    [snapshot] = host.repository.snapshots
    assert f"The pre-upgrade backup is snapshot {snapshot.id[:8]}" in capsys.readouterr().err


def test_a_new_setting_reaches_env_as_the_template_has_it(tmp_path: Path) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0")
    opt = installed_release(tmp_path)
    bundle = release_bundle(tmp_path)
    with (bundle / "env.template").open("a") as template:
        template.write("# How many turns a visitor may send per hour.\n# SC_VISITOR_TURNS=20\n")

    assert upgrade(host, opt, bundle) == 0

    assert "# SC_VISITOR_TURNS=20" in (opt / ".env").read_text().splitlines()


def test_a_rollback_leaves_only_the_previous_releases_files(tmp_path: Path) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0", failing_migrations={"1.5.0"})
    opt = installed_release(tmp_path)  # from before bundles carried release.txt

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    assert not (opt / "release.txt").exists()


def test_a_rollback_that_cannot_put_the_old_files_back_restores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0", failing_migrations={"1.5.0"})
    opt = installed_release(tmp_path)
    copy = sc.shutil.copy2

    def full_disk_for_previous(source: Path, destination: Path) -> object:
        if Path(source).parent.name == "previous" and Path(destination).parent == opt:
            raise OSError(28, "No space left on device")
        return copy(source, destination)

    monkeypatch.setattr(sc.shutil, "copy2", full_disk_for_previous)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    assert not any("pg_restore" in ran.args for ran in host.ran)
    error = capsys.readouterr().err
    assert "The rollback failed" in error and "previous" in error


def test_an_upgrade_without_docker_says_so_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.4.0", failing={"docker info"})
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 1

    error = capsys.readouterr().err
    assert "Docker is not running" in error and "Nothing was changed." in error


def test_an_upgrade_keeps_the_install_date(tmp_path: Path) -> None:
    host = FakeHost(running="1.4.0", schema="1.4.0")
    opt = installed_release(tmp_path)

    assert upgrade(host, opt, release_bundle(tmp_path)) == 0

    lines = (opt / ".installed").read_text().splitlines()
    assert "installed=2026-09-01T03:00:00+0000" in lines
    assert "version=1.5.0" in lines and "upgraded_from=1.4.0" in lines

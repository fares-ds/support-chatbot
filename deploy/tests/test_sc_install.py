import ast
import stat
import sys
from pathlib import Path

import pytest
from conftest import DEPLOY, FakeHost, bundle, sc

TOKEN = "ghp_" + "x" * 36


def install(host: FakeHost, tmp_path: Path, domain: str = "chat.example.com") -> int:
    (tmp_path / "cron.d").mkdir(exist_ok=True)
    unpacked = tmp_path / "bundle"
    if not unpacked.exists():
        bundle(unpacked)
        (unpacked / "compose.yaml").write_text(
            "services:\n  api:\n    image: ghcr.io/fares-ds/support-chatbot-backend:1.4.0\n"
        )
    return sc.install(
        host,
        bundle=unpacked,
        install_dir=tmp_path / "opt",
        domain=domain,
        registry_user="fares-ds-installs",
        token=TOKEN,
        settings={"SC_EMBEDDING_MODEL": "intfloat/multilingual-e5-small"},
        cron_file=tmp_path / "cron.d" / "support-chatbot",
    )


def steps(host: FakeHost) -> list[str]:
    """What the install did, without the read-only probes of its prerequisite checks."""
    probes = (["docker", "version"], ["docker", "info"])
    return [
        " ".join(ran.args[:4])
        for ran in host.ran
        if ran.args[:2] not in probes and ran.args[:3] != ["docker", "compose", "version"]
    ]


def test_a_fresh_install_runs_its_steps_in_order_as_the_service_account(
    host: FakeHost, tmp_path: Path
) -> None:
    assert install(host, tmp_path) == 0

    assert steps(host) == [
        "useradd supportchatbot",
        "docker login ghcr.io --username",
        "docker compose --profile tools",  # pulls restic's image too, for the first backup
        "docker compose run --rm",
        "docker compose up --detach",
        "fetch https://chat.example.com/api/health",
    ]
    probes = (["docker", "version"], ["docker", "info"], ["docker", "compose", "version"])
    installing = [
        ran
        for ran in host.ran
        if ran.args[0] == "docker" and ran.args[:2] not in probes and ran.args[:3] not in probes
    ]
    assert {ran.user for ran in installing} == {"supportchatbot"}
    assert sorted(path.name for path in (tmp_path / "opt").iterdir()) == [
        ".env",
        ".installed",
        "Caddyfile",
        "README.md",
        "compose.yaml",
        "env.template",
        "sc",
    ]
    assert "1.4.0" in (tmp_path / "opt" / ".installed").read_text()


def test_the_token_and_the_secrets_never_reach_arguments_or_output(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install(host, tmp_path)

    secrets = [
        line.split("=", 1)[1]
        for line in (tmp_path / "opt" / ".env").read_text().splitlines()
        if line.startswith(("SC_POSTGRES_PASSWORD=", "SC_ENCRYPTION_KEY=", "SC_RESTIC_PASSWORD="))
    ]
    output = capsys.readouterr()
    for secret in [TOKEN, *secrets]:
        assert secret not in output.out + output.err
        assert all(secret not in " ".join(ran.args) for ran in host.ran)
    [login] = [ran for ran in host.ran if ran.args[:2] == ["docker", "login"]]
    assert login.input == TOKEN


def test_a_missing_prerequisite_stops_before_anything_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(compose=None)

    assert install(host, tmp_path) == 1

    assert not (tmp_path / "opt").exists()
    assert steps(host) == []
    assert "Docker Compose is not installed" in capsys.readouterr().err


def test_a_finished_install_refuses_to_run_again(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install(host, tmp_path)
    environment = (tmp_path / "opt" / ".env").read_text()
    again = FakeHost(users={"supportchatbot"})

    assert install(again, tmp_path) == 1

    assert (tmp_path / "opt" / ".env").read_text() == environment
    assert again.ran == []
    assert "already installed" in capsys.readouterr().err


def test_a_failed_step_keeps_the_secrets_for_the_next_run(tmp_path: Path) -> None:
    assert install(FakeHost(failing={"docker login"}), tmp_path) == 1
    environment = (tmp_path / "opt" / ".env").read_text()
    assert not (tmp_path / "opt" / ".installed").exists()

    assert install(FakeHost(users={"supportchatbot"}), tmp_path) == 0

    assert (tmp_path / "opt" / ".env").read_text() == environment


def test_localhost_is_checked_with_caddys_own_certificate_authority(
    host: FakeHost, tmp_path: Path
) -> None:
    install(host, tmp_path, domain="localhost")

    copied = [ran for ran in host.ran if ran.args[:3] == ["docker", "compose", "cp"]]
    assert copied and copied[0].args[3].startswith("caddy:/data/caddy/pki/authorities/local/")
    assert steps(host)[-1] == "fetch https://localhost/api/health"


def test_an_unhealthy_install_is_reported_and_not_marked_installed(tmp_path: Path) -> None:
    host = FakeHost(health='{"status": "down"}')
    (tmp_path / "cron.d").mkdir()

    assert (
        sc.install(  # a short wait, so the test does not sit through the real one
            host,
            bundle=bundle(tmp_path / "bundle"),
            install_dir=tmp_path / "opt",
            domain="chat.example.com",
            registry_user="u",
            token=TOKEN,
            settings={},
            cron_file=tmp_path / "cron.d" / "support-chatbot",
            health_timeout=0,
        )
        == 1
    )

    assert not (tmp_path / "opt" / ".installed").exists()


def test_a_rerun_after_a_failed_health_check_passes_its_own_ports(tmp_path: Path) -> None:
    unhealthy = FakeHost(health='{"status": "down"}')
    assert install_quickly(unhealthy, tmp_path) == 1
    # The stack it started now holds the ports.
    again = FakeHost(users={"supportchatbot"}, busy_ports={80, 443})

    assert install_quickly(again, tmp_path) == 0


def test_a_rerun_with_a_corrected_domain_checks_that_domain(tmp_path: Path) -> None:
    assert install_quickly(FakeHost(failing={"docker login"}), tmp_path, "chat.exampel.com") == 1
    host = FakeHost(users={"supportchatbot"})

    assert install_quickly(host, tmp_path, "chat.example.com") == 0

    assert steps(host)[-1] == "fetch https://chat.example.com/api/health"
    assert "SC_DOMAIN=chat.example.com" in (tmp_path / "opt" / ".env").read_text()


def test_caddys_certificate_authority_is_copied_once_caddy_has_made_it(tmp_path: Path) -> None:
    host = FakeHost(fail_times={"docker compose cp": 2})

    assert install_quickly(host, tmp_path, "localhost") == 0


def test_an_existing_service_account_joins_the_docker_group(tmp_path: Path) -> None:
    host = FakeHost(users={"supportchatbot"})

    assert install(host, tmp_path) == 0

    assert host.groups["docker"] == {"supportchatbot"}


def install_quickly(host: FakeHost, tmp_path: Path, domain: str = "chat.example.com") -> int:
    """sc install with short pauses between health checks, and half a second in all."""
    (tmp_path / "cron.d").mkdir(exist_ok=True)
    unpacked = tmp_path / "bundle"
    if not unpacked.exists():
        bundle(unpacked)
    return sc.install(
        host,
        bundle=unpacked,
        install_dir=tmp_path / "opt",
        domain=domain,
        registry_user="u",
        token=TOKEN,
        settings={},
        cron_file=tmp_path / "cron.d" / "support-chatbot",
        health_timeout=0.5,
        retry_every=0.01,
    )


def test_the_install_schedules_a_daily_backup_as_the_service_account(
    host: FakeHost, tmp_path: Path
) -> None:
    assert install(host, tmp_path) == 0

    cron = tmp_path / "cron.d" / "support-chatbot"
    [entry] = [line for line in cron.read_text().splitlines() if line and line[0].isdigit()]
    minute, hour, day, month, weekday, user, command = entry.split(maxsplit=6)
    assert (day, month, weekday) == ("*", "*", "*")
    assert 0 <= int(minute) < 60 and 0 <= int(hour) < 24
    assert user == "supportchatbot"
    assert command.startswith(f"{tmp_path / 'opt' / 'sc'} backup ")
    assert stat.S_IMODE(cron.stat().st_mode) == 0o644


def test_the_install_ends_by_asking_for_env_in_the_password_manager(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert install(host, tmp_path) == 0

    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert "password manager" in last
    assert str(tmp_path / "opt" / ".env") in last


def test_a_failed_install_schedules_nothing(tmp_path: Path) -> None:
    assert install(FakeHost(failing={"docker login"}), tmp_path) == 1

    assert not (tmp_path / "cron.d" / "support-chatbot").exists()


def test_sc_imports_only_the_standard_library() -> None:
    tree = ast.parse((DEPLOY / "sc").read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported <= sys.stdlib_module_names, imported - sys.stdlib_module_names

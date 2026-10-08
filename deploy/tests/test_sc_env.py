import base64
import re
import stat
from pathlib import Path

import pytest
from conftest import FakeHost, bundle, sc


def env_values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if re.match(r"^SC_\w+=", line)
    )


def write(host: FakeHost, tmp_path: Path, settings: dict[str, str] | None = None) -> Path:
    template = (bundle(tmp_path / "bundle") / "env.template").read_text()
    path = tmp_path / "install" / ".env"
    path.parent.mkdir(exist_ok=True)
    sc.write_env(
        host, path, template, domain="chat.example.com", settings=settings or {}, owner="svc"
    )
    return path


def test_the_environment_file_holds_the_domain_random_secrets_and_settings(
    host: FakeHost, tmp_path: Path
) -> None:
    path = write(host, tmp_path, {"SC_EMBEDDING_MODEL": "intfloat/multilingual-e5-small"})

    values = env_values(path)
    assert values["SC_DOMAIN"] == "chat.example.com"
    assert re.fullmatch(r"[0-9a-f]{64}", values["SC_POSTGRES_PASSWORD"])
    assert len(base64.urlsafe_b64decode(values["SC_ENCRYPTION_KEY"])) == 32
    assert re.fullmatch(r"[0-9a-f]{64}", values["SC_RESTIC_PASSWORD"])
    assert values["SC_EMBEDDING_MODEL"] == "intfloat/multilingual-e5-small"
    assert "# SC_HTTP_PORT=80" in path.read_text()  # untouched defaults stay commented


def test_only_the_service_account_can_read_it(host: FakeHost, tmp_path: Path) -> None:
    path = write(host, tmp_path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert host.owners[path] == "svc"


def test_every_install_gets_its_own_secrets(tmp_path: Path) -> None:
    first = env_values(write(FakeHost(), tmp_path / "a"))
    second = env_values(write(FakeHost(), tmp_path / "b"))

    assert first["SC_POSTGRES_PASSWORD"] != second["SC_POSTGRES_PASSWORD"]
    assert first["SC_ENCRYPTION_KEY"] != second["SC_ENCRYPTION_KEY"]


def test_a_rerun_keeps_the_secrets_and_takes_the_corrected_domain_and_settings(
    host: FakeHost, tmp_path: Path
) -> None:
    path = write(host, tmp_path)
    before = env_values(path)
    template = (tmp_path / "bundle" / "env.template").read_text()

    written = sc.write_env(
        host,
        path,
        template,
        domain="support.example.com",
        settings={"SC_HTTPS_PORT": "8443"},
        owner="svc",
    )

    after = env_values(path)
    assert written is False
    assert after["SC_POSTGRES_PASSWORD"] == before["SC_POSTGRES_PASSWORD"]
    assert after["SC_ENCRYPTION_KEY"] == before["SC_ENCRYPTION_KEY"]
    assert after["SC_DOMAIN"] == "support.example.com"
    assert after["SC_HTTPS_PORT"] == "8443"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("given", "named"),
    [
        (["SC_POSTGRES_PASSWORD=hunter2"], "generates"),
        (["SC_ENCRYPTION_KEY=abc"], "generates"),
        (["SC_RESTIC_PASSWORD=abc"], "generates"),
        (["SC_RESTIC_AWS_SECRET_ACCESS_KEY=abc"], "edit .env"),
        (["SC_RESTIC_REPOSITORY=rest:https://acme:hunter2@backup.example.com/acme"], "edit .env"),
        (["PATH=/tmp"], "SC_"),
        (["SC_EMBEDDING_MODEL"], "KEY=VALUE"),
        (["SC_HTTP_PORT=eighty"], "port"),
        (["SC_HTTPS_PORT=70000"], "port"),
        (["SC_EMBEDDING_MODEL=e5\nSC_POSTGRES_PASSWORD=x"], "one line"),
    ],
)
def test_a_setting_that_is_a_secret_or_malformed_is_refused(given: list[str], named: str) -> None:
    with pytest.raises(ValueError, match=named):
        sc.parse_settings(given)


@pytest.mark.parametrize("domain", ["chat.example.com", "localhost", "xn--mgbh0fb.example"])
def test_a_domain_is_a_host_name(domain: str) -> None:
    assert sc.check_domain(domain) == domain


@pytest.mark.parametrize(
    "domain", ["https://chat.example.com", "chat.example.com/path", "a b.com", "x\nSC_A=1", ""]
)
def test_anything_else_is_refused_as_a_domain(domain: str) -> None:
    with pytest.raises(ValueError, match="domain"):
        sc.check_domain(domain)


def test_a_rerun_generates_a_secret_the_existing_file_lacks_and_keeps_the_others(
    host: FakeHost, tmp_path: Path
) -> None:
    # Written by a bundle from before backups: no restic password.
    path = write(host, tmp_path)
    before = env_values(path)
    path.write_text(
        "".join(
            line + "\n"
            for line in path.read_text().splitlines()
            if not line.startswith("SC_RESTIC_PASSWORD=")
        )
    )
    template = (tmp_path / "bundle" / "env.template").read_text()

    sc.write_env(host, path, template, domain="chat.example.com", settings={}, owner="svc")

    after = env_values(path)
    assert re.fullmatch(r"[0-9a-f]{64}", after["SC_RESTIC_PASSWORD"])
    assert after["SC_ENCRYPTION_KEY"] == before["SC_ENCRYPTION_KEY"]
    assert after["SC_POSTGRES_PASSWORD"] == before["SC_POSTGRES_PASSWORD"]

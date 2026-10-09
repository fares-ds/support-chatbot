import json
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import FakeHost, installed, sc


def healthy_install(tmp_path: Path, backed_up_hours_ago: float = 6) -> Path:
    """An install of 1.5.0, upgraded from 1.4.0, whose last backup succeeded."""
    opt = installed(tmp_path)
    (opt / ".installed").write_text(
        "version=1.5.0\ninstalled=2026-09-01T03:00:00+0000\n"
        "upgraded_from=1.4.0\nupgraded=2026-10-09T02:00:00+0000\n"
    )
    record_backup(opt, hours_ago=backed_up_hours_ago)
    return opt


def record_backup(opt: Path, *, hours_ago: float, last_ok: bool = True) -> None:
    at = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(time.time() - hours_ago * 3600))
    (opt / "backup-status.json").write_text(
        json.dumps(
            {
                "last_run": {
                    "at": at,
                    "ok": last_ok,
                    "snapshot": "3f2a9c1e" * 8 if last_ok else None,
                    "message": "Snapshot 3f2a9c1e saved." if last_ok else "Dumping failed: x",
                },
                "last_success": at if last_ok else None,
            }
        )
    )


def status(
    host: FakeHost, opt: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, str]]:
    """sc status's exit code, and each line's level and text by its label."""
    code = sc.status(host, install_dir=opt)
    lines = {}
    for line in capsys.readouterr().out.splitlines()[1:]:
        label, _, rest = line.partition("  ")
        if line.startswith("Status: "):
            label, rest = "Status", line.removeprefix("Status: ")
        lines[label.strip()] = rest.strip()
    return code, lines


def test_a_healthy_install_is_ok_on_every_line_and_exits_0(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host.running = "1.5.0"
    opt = healthy_install(tmp_path)

    code = sc.status(host, install_dir=opt)

    output = capsys.readouterr().out
    assert code == 0
    header, *lines = output.strip().splitlines()
    assert "Support Chatbot 1.5.0 at https://chat.example.com" in header
    assert "upgraded from 1.4.0" in header
    labels = [line.split("  ")[0] for line in lines[:-1]]
    assert labels == [
        "Services",
        "Models",
        "Health",
        "Disk",
        "Queue",
        "Last backup",
        "Registry token",
    ]
    assert all(" ok " in f" {line} " for line in lines[:-1])
    assert lines[-1] == "Status: ok"


def stopped_worker() -> FakeHost:
    host = FakeHost(running="1.5.0")
    host.services["worker"] = ("exited", "", 137)
    return host


def unhealthy_tei() -> FakeHost:
    host = FakeHost(running="1.5.0")
    host.services["tei-embed"] = ("running", "unhealthy", 0)
    return host


def no_health_endpoint() -> FakeHost:
    class CaddyDown(FakeHost):
        def fetch(self, url: str, cafile: Path | None) -> str:
            raise OSError("connection refused")

    return CaddyDown(running="1.5.0")


@pytest.mark.parametrize(
    ("make_host", "label", "named"),
    [
        (stopped_worker, "Services", "worker (exited)"),
        (unhealthy_tei, "Services", "tei-embed (unhealthy)"),
        (lambda: FakeHost(running="1.5.0", down_checks={"ollama"}), "Models", "down: ollama"),
        (lambda: FakeHost(running="1.5.0", down_checks={"worker"}), "Health", "down: worker"),
        (no_health_endpoint, "Models", "did not answer"),
        (lambda: FakeHost(running="1.5.0", free_gb=4), "Disk", "below 10 GB"),
        (
            lambda: FakeHost(running="1.5.0", token=PermissionError("refused")),
            "Registry token",
            "GitHub refused it",
        ),
        (
            lambda: FakeHost(running="1.5.0", token=datetime.now(timezone.utc) - timedelta(days=1)),
            "Registry token",
            "expired on",
        ),
    ],
)
def test_a_problem_is_named_on_its_line_and_exits_2(
    make_host: Callable[[], FakeHost],
    label: str,
    named: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, lines = status(make_host(), healthy_install(tmp_path), capsys)

    assert code == 2
    assert lines[label].startswith("problem") and named in lines[label]
    assert "problem" in lines["Status"]


@pytest.mark.parametrize(
    ("hours_ago", "last_ok", "level", "named"),
    [
        (30, True, "problem", "stale: the last success was"),
        (6, False, "problem", "no backup has succeeded yet"),
        (2, True, "ok", "snapshot 3f2a9c1e"),
    ],
)
def test_the_last_backup_must_have_succeeded_within_26_hours(
    hours_ago: float,
    last_ok: bool,
    level: str,
    named: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opt = healthy_install(tmp_path)
    record_backup(opt, hours_ago=hours_ago, last_ok=last_ok)

    code, lines = status(FakeHost(running="1.5.0"), opt, capsys)

    assert lines["Last backup"].startswith(level) and named in lines["Last backup"]
    assert code == (2 if level == "problem" else 0)


def test_an_install_whose_backup_never_ran_has_a_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = healthy_install(tmp_path)
    (opt / "backup-status.json").unlink()

    code, lines = status(FakeHost(running="1.5.0"), opt, capsys)

    assert code == 2
    assert (
        lines["Last backup"].startswith("problem")
        and "no backup has run yet" in lines["Last backup"]
    )


def test_a_failed_run_after_a_recent_success_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = healthy_install(tmp_path)
    record = json.loads((opt / "backup-status.json").read_text())
    record["last_run"] = {
        "at": record["last_success"],
        "ok": False,
        "snapshot": None,
        "message": "Saving the snapshot to the repository failed: timeout",
    }
    (opt / "backup-status.json").write_text(json.dumps(record))

    code, lines = status(FakeHost(running="1.5.0"), opt, capsys)

    assert code == 1
    assert (
        lines["Last backup"].startswith("warning") and "the last run failed" in lines["Last backup"]
    )


@pytest.mark.parametrize(
    ("token", "level", "named"),
    [
        (
            datetime.now(timezone.utc) + timedelta(days=5),
            "warning",
            "in 5 days: generate a new one",
        ),
        (datetime.now(timezone.utc) + timedelta(days=40), "ok", "in 40 days"),
        (None, "ok", "never expires"),
        (LookupError("no ghcr.io login in /opt/x"), "warning", "log in again"),
        (OSError("timed out"), "warning", "could not be asked"),
    ],
)
def test_the_registry_token_warns_two_weeks_before_it_expires(
    token: object, level: str, named: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = status(FakeHost(running="1.5.0", token=token), healthy_install(tmp_path), capsys)  # type: ignore[arg-type]

    assert lines["Registry token"].startswith(level) and named in lines["Registry token"]
    assert code == (1 if level == "warning" else 0)


def test_the_queue_shows_how_many_jobs_wait(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.5.0", queue=["ingest", "ingest", "re-embed"])

    _, lines = status(host, healthy_install(tmp_path), capsys)

    assert lines["Queue"] == "ok       3 jobs waiting"


def test_status_shows_no_secret_and_no_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeHost(running="1.5.0", database=b"PGDMP Customer: my card was charged twice")
    opt = healthy_install(tmp_path)

    sc.status(host, install_dir=opt)

    output = capsys.readouterr()
    secrets = [
        line.split("=", 1)[1]
        for line in (opt / ".env").read_text().splitlines()
        if "KEY=" in line or "PASSWORD=" in line
    ]
    for text in [*secrets, "charged twice"]:
        assert text not in output.out + output.err


def test_status_without_an_install_exits_2(
    host: FakeHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sc.status(host, install_dir=tmp_path / "opt") == 2

    assert "not installed" in capsys.readouterr().err


@pytest.mark.parametrize(
    "header", ["2026-12-31 18:30:00 UTC", "2027-01-01 01:30:00 +0700", "2027-01-01 01:30:00 +07:00"]
)
def test_githubs_expiry_header_is_read_with_an_offset_or_utc(header: str) -> None:
    assert sc.github_expiry(header) == datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc)


def test_the_real_host_reads_the_body_of_a_503_where_health_names_what_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import urllib.error

    body = b'{"status": "down", "checks": {"ollama": "down"}}'

    def unhealthy(url: str, **kwargs: object) -> object:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(body))  # type: ignore[arg-type]

    monkeypatch.setattr(sc.urllib.request, "urlopen", unhealthy)

    assert sc.Host().fetch("https://chat.example.com/api/health", None) == body.decode()


def test_an_unreadable_backup_record_is_a_problem_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opt = healthy_install(tmp_path)
    (opt / "backup-status.json").write_text('["not", "a", "record"]')

    code, lines = status(FakeHost(running="1.5.0"), opt, capsys)

    assert code == 2
    assert lines["Last backup"].startswith("problem")
    assert lines["Registry token"].startswith("ok")  # the lines after it still print


def test_one_stopped_container_of_a_service_is_not_hidden_by_another(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class TwoWorkers(FakeHost):
        def run(self, args: list[str], **kwargs: object) -> str:
            if args[2:3] == ["ps"]:
                rows = [
                    {"Service": "worker", "State": "exited", "Health": "", "ExitCode": 137},
                    {"Service": "worker", "State": "running", "Health": "healthy", "ExitCode": 0},
                ]
                others = super().run(args, **kwargs)  # type: ignore[arg-type]
                return "\n".join([json.dumps(row) for row in rows] + others.splitlines()[1:])
            return super().run(args, **kwargs)  # type: ignore[arg-type]

    code, lines = status(TwoWorkers(running="1.5.0"), healthy_install(tmp_path), capsys)

    assert code == 2 and "worker (exited)" in lines["Services"]


def test_a_token_expiring_within_a_day_says_how_many_hours(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    token = datetime.now(timezone.utc) + timedelta(hours=12, minutes=5)

    _, lines = status(FakeHost(running="1.5.0", token=token), healthy_install(tmp_path), capsys)

    assert "in 12 hours" in lines["Registry token"]


def test_a_login_kept_by_a_credential_helper_is_named_as_such(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"auths": {"ghcr.io": {}}, "credsStore": "pass"}')

    with pytest.raises(LookupError, match="credential helper"):
        sc.Host().registry_token_expiry(config)


def test_a_malformed_token_never_reaches_the_output(tmp_path: Path) -> None:
    import base64

    secret = "ghp_" + "s" * 36
    config = tmp_path / "config.json"
    auth = base64.b64encode(f"u:{secret}\n\n".encode()).decode()  # pasted with newlines
    config.write_text(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}))

    with pytest.raises(LookupError) as raised:
        sc.Host().registry_token_expiry(config)

    assert secret not in str(raised.value) and secret not in repr(raised.value)

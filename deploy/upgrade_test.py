#!/usr/bin/env python3
"""The upgrade test (OPS-4, ADR-0013): every release must upgrade a copy of the previous
release's seeded database, and the previous release must still run on the result, which is what
makes `sc upgrade`'s rollback to the previous images safe.

    python3 deploy/upgrade_test.py --candidate 0.0.0

The candidate's backend image must already be built, tagged with --candidate. The previous
release is the newest published GitHub release, or the newest before --release-tag. Its bundle
comes from that release (through `gh`), and Compose pulls its images. Then:

1. The previous release migrates an empty database, which the seeds fill; every table needs rows.
2. Its API and worker pass the smoke test.
3. The candidate migrates the database, its own seeds fill its new tables, and it passes.
4. The previous release starts again on the migrated database and passes: the rollback case.
5. A negative control renames a column the previous release reads, and its smoke test must fail.

With no previous release, the candidate migrates an empty database and passes the smoke test.

The smoke test: a release's migration job, API and worker start; Postgres and Valkey answer;
and the worker writes a heartbeat after the start, which the API reads back.

Standard library only, like sc. Runs in CI's `upgrade` job and on a machine with Docker.
"""

import sys

if sys.version_info < (3, 10):  # noqa: UP036 - a plain message, before anything 3.9 cannot parse
    sys.exit(f"The upgrade test needs Python 3.10 or later; this is {sys.version.split()[0]}.")

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import re
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMPOSE = ROOT / "deploy" / "compose.yaml"
MIGRATIONS = ROOT / "backend" / "migrations" / "versions"
SEEDS = ROOT / "backend" / "tests" / "upgrade_seeds"
BACKEND = "ghcr.io/fares-ds/support-chatbot-backend"
PROJECT = "sc-upgrade-test"
"""Its own Compose project, so a development stack on the same machine is left alone."""
SMOKE_SECONDS = 150
"""A started worker beats within its first 30 s; room for slow starts."""
NEGATIVE_SECONDS = 75
"""Two beats of a worker already running: enough for a fresh beat that never comes."""
CANARY = ("heartbeats", "beat_at")
"""A column every release so far reads. The negative control renames it. If a contract step
ever drops it, choose another column the previous release reads."""

_RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_SEED = re.compile(r"^(\d+)\.sql$")
_REVISION = re.compile(r"^(\d+)_")


def seeds(directory: Path, *, after: str | None, through: str) -> list[Path]:
    """The seed files for the revisions after `after` (or from the first) through `through`.
    A seed is named after the migration revision whose tables or columns it fills."""
    low = int(after) if after is not None else -1
    found = [
        (int(match.group(1)), path)
        for path in directory.iterdir()
        if (match := _SEED.match(path.name))
    ]
    return [path for number, path in sorted(found) if low < number <= int(through)]


def previous_release(tags: Iterable[str], *, building: str | None) -> str | None:
    """The release to upgrade from: the newest one for a pull request, or the newest before the
    release tag being built. None when there is none, as for the first release."""
    releases = sorted(
        (tuple(int(part) for part in match.groups()), tag[1:])
        for tag in tags
        if (match := _RELEASE.match(tag))
    )
    if building is not None:
        built = _RELEASE.match(building)
        if built is None:
            raise ValueError(f"not a release tag: {building}")
        limit = tuple(int(part) for part in built.groups())
        releases = [release for release in releases if release[0] < limit]
    return releases[-1][1] if releases else None


class Failed(Exception):
    """A step of the test failed; the message says which and why."""


class SmokeFailed(Failed):
    """A release ran, but failed the smoke test."""


def run(
    args: Sequence[str],
    *,
    input: str | None = None,
    cwd: Path | None = None,
    shown: Sequence[str] | None = None,
) -> str:
    """Runs a command and returns its output. A failure names the command as `shown`."""
    done = subprocess.run(
        list(args), input=input, cwd=cwd, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        output = (done.stderr or done.stdout).strip()[-2000:]
        command = " ".join(shown if shown is not None else args[:6])
        raise Failed(f"`{command}` exited {done.returncode}: {output}")
    return done.stdout.strip()


@dataclass(frozen=True)
class Release:
    """One release's Compose file, on the test's shared project, volumes and settings."""

    name: str
    compose: Path
    env_file: Path

    def compose_run(self, *args: str, input: str | None = None) -> str:
        return run(
            [
                "docker", "compose", "--project-name", PROJECT,
                "--file", str(self.compose), "--env-file", str(self.env_file), *args,
            ],
            input=input,
            shown=["docker", "compose", *args[:5]],
        )  # fmt: skip

    def sql(self, statement: str, *, input: str | None = None) -> str:
        return self.compose_run(
            "exec", "-T", "postgres",
            "psql", "--username=sc", "--dbname=support_chatbot", "--no-psqlrc",
            "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
            *(["--command", statement] if statement else ["--file=-"]),
            input=input,
        )  # fmt: skip

    def migrate(self) -> str:
        """Runs the release's migration job, and returns the database's revision."""
        self.compose_run("up", "--detach", "--wait", "postgres", "valkey")
        self.compose_run("run", "--rm", "migrate")
        return self.sql("SELECT version_num FROM alembic_version")

    def seed(self, files: list[Path]) -> None:
        for path in files:
            _say(f"  seeding {path.name}")
            try:
                self.sql("", input=path.read_text(encoding="utf-8"))
            except Failed as error:
                raise Failed(f"The seed {path.name} failed on {self.name}: {error}") from None

    def empty_tables(self) -> list[str]:
        tables = self.sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            " AND table_type = 'BASE TABLE' AND table_name <> 'alembic_version' ORDER BY 1"
        ).split()
        if not tables:
            return []
        # One query: each table's name when it has no rows. Names come from the catalogue,
        # quoted as identifiers and as literals.
        query = " UNION ALL ".join(
            f"SELECT {_literal(table)} WHERE NOT EXISTS (SELECT 1 FROM {_identifier(table)})"  # noqa: S608 - catalogue names, quoted
            for table in tables
        )
        return self.sql(query).split()

    def smoke(self, *, timeout: float = SMOKE_SECONDS) -> None:
        """The release's API and worker start on the database, Postgres and Valkey answer, and
        the worker writes a heartbeat after the start that the API reads back."""
        started = _timestamp(
            self.sql("SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US')")
        )
        self.compose_run("up", "--detach", "--wait", "--wait-timeout", "300", "api", "worker")
        deadline = time.monotonic() + timeout
        last = "no answer yet"
        while time.monotonic() < deadline:
            report = self._health()
            checks = report.get("checks", {})
            beat = report.get("worker_heartbeat")
            if (
                beat
                and _timestamp(beat) > started
                and all(checks.get(name) == "ok" for name in ("postgres", "valkey", "worker"))
            ):
                return
            last = json.dumps({"checks": checks, "worker_heartbeat": beat})
            time.sleep(3)
        raise SmokeFailed(f"{self.name} failed the smoke test after {timeout:.0f} s: {last}")

    def stop_app(self) -> None:
        self.compose_run("stop", "api", "worker")

    def _health(self) -> dict[str, Any]:
        """GET /api/health from inside the API's container: model services are not started, so
        the status is 503, and the checks that matter are read from the body."""
        script = (
            "import urllib.request, urllib.error\n"
            "url = 'http://127.0.0.1:8000/api/health'\n"
            "try:\n"
            "    body = urllib.request.urlopen(url, timeout=5).read()\n"
            "except urllib.error.HTTPError as error:\n"
            "    body = error.read()\n"
            "print(body.decode())\n"
        )
        try:
            report: dict[str, Any] = json.loads(
                self.compose_run("exec", "-T", "api", "python", "-c", script)
            )
        except (Failed, ValueError):
            return {}
        return report


def _timestamp(text: str) -> datetime:
    """A UTC time, from Postgres or from the API's JSON (which Python 3.10 cannot parse with Z)."""
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def candidate_head() -> str:
    numbers = [m.group(1) for path in MIGRATIONS.iterdir() if (m := _REVISION.match(path.name))]
    return max(numbers, key=int)


def previous_bundle(version: str, directory: Path) -> Path:
    """The previous release's bundle, from its GitHub release, checked against its checksum."""
    if not hasattr(tarfile, "data_filter"):
        raise Failed("This Python cannot extract archives safely: use 3.10.12, 3.11.4 or later.")
    archive = f"support-chatbot-{version}.tar.gz"
    run(
        ["gh", "release", "download", f"v{version}", "--pattern", f"{archive}*", "--dir",
         str(directory)],
        cwd=ROOT,  # gh finds the repository from the checkout, wherever this runs from
    )  # fmt: skip
    expected = (directory / f"{archive}.sha256").read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256((directory / archive).read_bytes()).hexdigest()
    if actual != expected:
        raise Failed(f"{archive} does not match its checksum")
    with tarfile.open(directory / archive) as bundle:
        bundle.extractall(directory, filter="data")
    return directory / f"support-chatbot-{version}" / "compose.yaml"


def write_env(path: Path, candidate: str) -> None:
    """One install's settings, shared by both releases as an upgrade shares .env, with the
    secrets sc install generates. SC_VERSION names the candidate's images; the previous bundle
    pins its own."""
    loader = importlib.machinery.SourceFileLoader("sc", str(ROOT / "deploy" / "sc"))
    spec = importlib.util.spec_from_loader("sc", loader)
    if spec is None:
        raise Failed("deploy/sc could not be loaded")
    sc = importlib.util.module_from_spec(spec)
    loader.exec_module(sc)
    values = {"SC_VERSION": candidate, "SC_DOMAIN": "localhost"}
    values |= {key: make() for key, make in sc.GENERATED.items()}
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), "utf-8")


def check_seeded(release: Release, revision: str) -> None:
    empty = release.empty_tables()
    if empty:
        raise Failed(
            f"No seed rows at revision {revision} in: {', '.join(empty)}. Add"
            f" backend/tests/upgrade_seeds/<revision>.sql for the migration that made them."
        )


def upgrade_test(candidate: str, previous: str | None, work: Path) -> None:
    env_file = work / "upgrade.env"
    write_env(env_file, candidate)
    new = Release(f"the candidate ({candidate})", CANDIDATE_COMPOSE, env_file)
    head = candidate_head()
    tear_down(new)
    try:
        if previous is None:
            _say("No previous release: the candidate migrates an empty database.")
            _check_revision(new.migrate(), head)
            new.seed(seeds(SEEDS, after=None, through=head))
            check_seeded(new, head)
            _say(f"Smoke test: {new.name}...")
            new.smoke()
            return

        _say(f"Fetching {previous}'s bundle...")
        old = Release(
            f"the previous release ({previous})", previous_bundle(previous, work), env_file
        )
        _say(f"Migrating an empty database with {old.name}...")
        old_revision = old.migrate()
        if int(old_revision) > int(head):
            raise Failed(
                f"{old.name} is at revision {old_revision}, past this branch's head {head}:"
                " rebase the branch onto main."
            )
        old.seed(seeds(SEEDS, after=None, through=old_revision))
        check_seeded(old, old_revision)
        _say(f"Smoke test: {old.name}, on its own schema ({old_revision})...")
        old.smoke()
        old.stop_app()

        _say(f"Upgrading with {new.name}...")
        _check_revision(new.migrate(), head)
        new.seed(seeds(SEEDS, after=old_revision, through=head))
        check_seeded(new, head)
        _say(f"Smoke test: {new.name}, on the upgraded schema ({head})...")
        new.smoke()
        new.stop_app()

        _say(f"Smoke test: {old.name}, back on the upgraded schema, as after a rollback...")
        old.smoke()

        table, column = CANARY
        _say(f"Negative control: renaming {table}.{column}, which {old.name} reads...")
        old.sql(f"ALTER TABLE {table} RENAME COLUMN {column} TO {column}_renamed")
        try:
            old.smoke(timeout=NEGATIVE_SECONDS)
        except SmokeFailed:
            _say("  it failed the smoke test, as it should.")
        else:
            raise Failed("The negative control passed: the smoke test cannot see a broken schema.")
    except Failed:
        _say("Logs of the migration job, the API and the worker:")
        try:
            _say(new.compose_run("logs", "--no-color", "--tail", "60", "migrate", "api", "worker"))
        except Failed as error:
            _say(str(error))
        raise
    finally:
        try:
            tear_down(new)
        except Failed as error:  # never hide the test's own result
            _say(f"Warning: cleaning up failed: {error}")


def tear_down(release: Release) -> None:
    """Removes the project's containers, networks and volumes, including volumes only the
    previous release's Compose file declares."""
    release.compose_run("down", "--remove-orphans")
    label = f"label=com.docker.compose.project={PROJECT}"
    volumes = run(["docker", "volume", "ls", "--quiet", "--filter", label]).split()
    if volumes:
        run(["docker", "volume", "rm", *volumes])


def _check_revision(revision: str, head: str) -> None:
    if revision != head:
        raise Failed(f"The candidate migrated to revision {revision}, not its head {head}.")


def _say(message: str) -> None:
    print(message, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--candidate", required=True, help="the candidate images' tag, built")
    parser.add_argument("--release-tag", help="the vX.Y.Z tag being released, if one is")
    parser.add_argument(
        "--previous",
        help="the release to upgrade from, X.Y.Z or none (default: the newest one published)",
    )
    arguments = parser.parse_args(argv)
    try:
        run(["docker", "image", "inspect", f"{BACKEND}:{arguments.candidate}"])
    except Failed:
        print(
            f"Build the candidate first: docker build --tag {BACKEND}:{arguments.candidate}"
            " backend",
            file=sys.stderr,
        )
        return 1
    if arguments.previous == "none":
        previous = None
    elif arguments.previous:
        previous = arguments.previous
    else:
        # Published releases, not tags: a tag whose release never published has no bundle.
        listed = run(
            ["gh", "release", "list", "--exclude-drafts", "--limit", "1000", "--json",
             "tagName,isPrerelease"],
            cwd=ROOT,
        )  # fmt: skip
        tags = [entry["tagName"] for entry in json.loads(listed) if not entry["isPrerelease"]]
        previous = previous_release(tags, building=arguments.release_tag)
    with tempfile.TemporaryDirectory(prefix="upgrade-test-") as work:
        try:
            upgrade_test(arguments.candidate, previous, Path(work))
        except Failed as error:
            print(f"The upgrade test failed: {error}", file=sys.stderr)
            return 1
    _say("The upgrade test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

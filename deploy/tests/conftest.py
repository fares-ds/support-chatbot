"""Loads `sc`, which has no .py extension so that the vendor runs it as ./sc, and fakes the host
it drives."""

import importlib.machinery
import importlib.util
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

DEPLOY = Path(__file__).resolve().parents[1]
DOCKER_ROOT = Path("/var/lib/docker")


def load_sc() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("sc", str(DEPLOY / "sc"))
    spec = importlib.util.spec_from_loader("sc", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sc"] = module
    loader.exec_module(module)
    return module


sc = load_sc()


@dataclass
class Ran:
    args: list[str]
    user: str | None
    input: str | None
    cwd: Path | None


STAGED: str = sc.STAGED
FILES: str = sc.FILES


@dataclass
class Snapshot:
    id: str
    time: str
    paths: list[str]
    host: str
    staged: dict[str, bytes]
    """The files sc staged in backup/, by name."""
    stored: dict[str, bytes]
    """The files volume, by path."""
    tags: list[str] = field(default_factory=list)


@dataclass
class FakeRepository:
    """A restic repository: what `restic backup` stored, and what `restore` and `dump` read."""

    exists: bool = True
    snapshots: list[Snapshot] = field(default_factory=list)

    def find(self, name: str) -> Snapshot | None:
        if name == "latest":
            return self.snapshots[-1] if self.snapshots else None
        return next((s for s in self.snapshots if s.id.startswith(name)), None)


@dataclass
class FakeHost:
    """A fresh Ubuntu host with Docker, where every check passes unless a test says otherwise."""

    root: bool = True
    python: tuple[int, int] = (3, 12)
    docker: str | None = "28.4.0"
    compose: str | None = "2.39.4"
    free_gb: float = 100
    docker_root_free_gb: float = 100
    """Free space where Docker keeps images and volumes."""
    docker_group: bool = True
    cron: bool = True
    busy_ports: set[int] = field(default_factory=set)
    users: set[str] = field(default_factory=set)
    failing: set[str] = field(default_factory=set)
    """Commands that fail, by their first two words, such as "docker login"."""
    fail_times: dict[str, int] = field(default_factory=dict)
    """Commands that fail this many times before they work, by their first three words."""
    groups: dict[str, set[str]] = field(default_factory=dict)
    """Group members added by sc."""
    health: str | None = None
    """What /api/health answers; None: the running release's own health (below)."""
    ran: list[Ran] = field(default_factory=list)
    owners: dict[Path, str] = field(default_factory=dict)
    database: bytes = b"PGDMP the database"
    """What pg_dump writes; pg_restore replaces it."""
    files: dict[str, bytes] = field(default_factory=lambda: {"kb/refunds.pdf": b"%PDF refunds"})
    """The files volume: uploads and parsed text."""
    queue: list[str] = field(default_factory=list)
    """Jobs waiting in Valkey."""
    repository: FakeRepository = field(default_factory=FakeRepository)
    running: str | None = None
    """The release whose containers run, from the Compose file `up` used."""
    schema: str | None = None
    """The release whose migration job last changed the schema."""
    failing_migrations: set[str] = field(default_factory=set)
    """Releases whose migration job fails."""
    unhealthy: set[str] = field(default_factory=set)
    """Releases that never report healthy."""
    breaking: set[str] = field(default_factory=set)
    """Releases whose migration breaks the releases before them."""
    silent: set[str] = field(default_factory=set)
    """Releases whose worker never writes a heartbeat."""
    last_beat: float = field(default_factory=time.time)
    """When a worker last beat: on starting, and once more as it stops."""

    def is_root(self) -> bool:
        return self.root

    def python_version(self) -> tuple[int, int]:
        return self.python

    def free_bytes(self, path: Path) -> int:
        gb = self.docker_root_free_gb if path == DOCKER_ROOT else self.free_gb
        return int(gb * 1024**3)

    def has_cron(self) -> bool:
        return self.cron

    def group_exists(self, name: str) -> bool:
        return name != "docker" or self.docker_group

    def add_to_group(self, user: str, group: str) -> None:
        self.groups.setdefault(group, set()).add(user)

    def port_busy(self, port: int) -> bool:
        return port in self.busy_ports

    def user_exists(self, name: str) -> bool:
        return name in self.users

    def add_system_user(self, name: str, home: Path) -> None:
        self.users.add(name)
        self.ran.append(Ran(["useradd", name], None, None, None))

    def chown(self, path: Path, user: str) -> None:
        self.owners[path] = user

    def run(
        self,
        args: list[str],
        *,
        user: str | None = None,
        input: str | None = None,
        cwd: Path | None = None,
        stdin_from: Path | None = None,
        stdout_to: Path | None = None,
    ) -> str:
        self.ran.append(Ran(list(args), user, input, cwd))
        if " ".join(args[:2]) in self.failing:
            raise sc.CommandFailed(args, "failed")
        key = " ".join(args[:3])
        if self.fail_times.get(key, 0) > 0:
            self.fail_times[key] -= 1
            raise sc.CommandFailed(args, "not yet")
        if "pg_dump" in args and stdout_to is not None:
            stdout_to.write_bytes(self.database)
            return ""
        if "valkey-cli" in args and "FLUSHALL" in args:
            self.queue.clear()
            return "OK"
        if "pg_restore" in args and stdin_from is not None:
            self.database = stdin_from.read_bytes()
            self.schema = None  # the backup's own schema
            return ""
        if args[:2] == ["docker", "compose"] and cwd is not None:
            release = _compose_release(args, cwd)
            if args[2:5] == ["run", "--rm", "migrate"]:
                if release in self.failing_migrations:
                    raise sc.CommandFailed(args, f"migration of {release} failed")
                self.schema = release
            elif "stop" in args:
                self.last_beat = time.time()  # the old worker's last beat, as it stops
            elif "up" in args:
                self.running = release
                if release not in self.silent:
                    self.last_beat = time.time()
        if args[:3] == ["docker", "compose", "run"] and "restic" in args:
            assert cwd is not None
            return self._restic(args, args[args.index("restic") + 1 :], cwd / "backup", stdout_to)
        if args[:2] == ["docker", "info"]:
            return str(DOCKER_ROOT)
        if args[:2] == ["docker", "version"]:
            if self.docker is None:
                raise sc.CommandFailed(args, "docker: command not found")
            return self.docker
        if args[:3] == ["docker", "compose", "version"]:
            if self.compose is None:
                raise sc.CommandFailed(args, "'compose' is not a docker command")
            return self.compose
        return ""

    def fetch(self, url: str, cafile: Path | None) -> str:
        self.ran.append(Ran(["fetch", url], None, None, None))
        if self.health is not None:
            return self.health
        release = self.running
        broken = self.schema in self.breaking and release != self.schema
        if release in self.unhealthy or broken:
            return '{"status": "down", "checks": {"postgres": "ok", "worker": "down"}}'
        beat = datetime.fromtimestamp(self.last_beat, timezone.utc).isoformat()
        return f'{{"status": "ok", "checks": {{"postgres": "ok"}}, "worker_heartbeat": "{beat}"}}'

    def _restic(
        self, args: list[str], command: list[str], staged: Path, stdout_to: Path | None
    ) -> str:
        """restic in its container: `staged` is the install's backup/ directory."""
        if not staged.exists():  # Docker makes a missing bind-mount source, as root
            staged.mkdir()
            self.owners[staged] = "root"
        if command[0] == "init":
            self.repository.exists = True
            return "created restic repository"
        if not self.repository.exists:
            raise sc.CommandFailed(args, "Fatal: repository does not exist", returncode=10)
        if command[:2] == ["cat", "config"]:
            return '{"version": 2}'
        if command[0] == "backup":
            snapshot = Snapshot(
                id=f"{len(self.repository.snapshots) + 1:08x}" * 8,
                time=f"2026-10-0{len(self.repository.snapshots) + 1}T03:17:02+00:00",
                paths=[arg for arg in command if arg.startswith("/")],
                tags=[command[i + 1] for i, arg in enumerate(command) if arg == "--tag"],
                host=command[command.index("--host") + 1],
                staged={path.name: path.read_bytes() for path in staged.iterdir()},
                stored=dict(self.files),
            )
            self.repository.snapshots.append(snapshot)
            return (
                '{"message_type": "status", "percent_done": 1}\n'
                f'{{"message_type": "summary", "snapshot_id": "{snapshot.id}"}}'
            )
        if command[0] == "snapshots":
            import json

            found = self.repository.find(command[-1])
            listed = [] if found is None else [{"id": found.id, "time": found.time}]
            return json.dumps(listed)
        if command[0] in ("dump", "restore"):
            found = self.repository.find(command[1])
            if found is None:
                raise sc.CommandFailed(
                    args, f"Fatal: no matching ID found for prefix {command[1]!r}"
                )
            if command[0] == "dump":
                content = found.staged[command[2].removeprefix(STAGED + "/")]
                if stdout_to is None:
                    return content.decode()
                stdout_to.write_bytes(content)
                return ""
            included = [command[i + 1] for i, arg in enumerate(command) if arg == "--include"]
            if STAGED in included:
                for name, content in found.staged.items():
                    (staged / name).write_bytes(content)
                # restic gives a directory its owner from the snapshot, by number: the old
                # server's service account, which may have had another uid.
                self.owners[staged] = "uid 997, the old server's service account"
            if FILES in included:
                self.files = dict(found.stored)
            return ""
        raise AssertionError(f"restic {command[0]} is not faked")


def bundle(directory: Path) -> Path:
    """An unpacked install bundle, as a release publishes it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "compose.yaml").write_text("name: support-chatbot\nservices: {}\n")
    (directory / "Caddyfile").write_text("{$SC_DOMAIN} {\n}\n")
    (directory / "README.md").write_text("# The install bundle\n")
    (directory / "env.template").write_text(
        "SC_DOMAIN=\n"
        "SC_POSTGRES_PASSWORD=\n"
        "SC_ENCRYPTION_KEY=\n"
        "SC_RESTIC_PASSWORD=\n"
        "SC_RESTIC_REPOSITORY=\n"
        "SC_RESTIC_AWS_ACCESS_KEY_ID=\n"
        "SC_RESTIC_AWS_SECRET_ACCESS_KEY=\n"
        "# SC_HTTP_PORT=80\n"
        "# SC_HTTPS_PORT=443\n"
        "# SC_EMBEDDING_MODEL=BAAI/bge-m3\n"
    )
    (directory / "sc").write_text("#!/usr/bin/env python3\n")
    return directory


KEY = "a2V5LW9mLXRoZS1pbnN0YWxsLXRoYXQtd2FzLWJhY2tlZC11cA=="
RESTIC_PASSWORD = "f" * 64


def installed(tmp_path: Path, **settings: str) -> Path:
    """An install that sc install finished, with a backup repository set."""
    opt = tmp_path / "opt"
    opt.mkdir(parents=True)
    values = {
        "SC_DOMAIN": "chat.example.com",
        "SC_POSTGRES_PASSWORD": "p" * 64,
        "SC_ENCRYPTION_KEY": KEY,
        "SC_RESTIC_REPOSITORY": "s3:https://s3.example.com/backups/acme",
        "SC_RESTIC_PASSWORD": RESTIC_PASSWORD,
        **settings,
    }
    (opt / ".env").write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    (opt / ".installed").write_text("version=1.4.0\n")
    return opt


def _compose_release(args: list[str], cwd: Path) -> str | None:
    """The release of the Compose file a command uses: --file's, or the one in `cwd`."""
    compose = cwd / (args[args.index("--file") + 1] if "--file" in args else "compose.yaml")
    if not compose.exists():
        return None
    match = re.search(r"support-chatbot-backend:(\S+)", compose.read_text())
    return match.group(1) if match else None


@pytest.fixture
def host() -> FakeHost:
    return FakeHost()

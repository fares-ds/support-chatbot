"""Loads `sc`, which has no .py extension so that the vendor runs it as ./sc, and fakes the host
it drives."""

import importlib.machinery
import importlib.util
import sys
from dataclasses import dataclass, field
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
    busy_ports: set[int] = field(default_factory=set)
    users: set[str] = field(default_factory=set)
    failing: set[str] = field(default_factory=set)
    """Commands that fail, by their first two words, such as "docker login"."""
    fail_times: dict[str, int] = field(default_factory=dict)
    """Commands that fail this many times before they work, by their first three words."""
    groups: dict[str, set[str]] = field(default_factory=dict)
    """Group members added by sc."""
    health: str = '{"status": "ok"}'
    ran: list[Ran] = field(default_factory=list)
    owners: dict[Path, str] = field(default_factory=dict)

    def is_root(self) -> bool:
        return self.root

    def python_version(self) -> tuple[int, int]:
        return self.python

    def free_bytes(self, path: Path) -> int:
        gb = self.docker_root_free_gb if path == DOCKER_ROOT else self.free_gb
        return int(gb * 1024**3)

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
    ) -> str:
        self.ran.append(Ran(list(args), user, input, cwd))
        if " ".join(args[:2]) in self.failing:
            raise sc.CommandFailed(args, "failed")
        key = " ".join(args[:3])
        if self.fail_times.get(key, 0) > 0:
            self.fail_times[key] -= 1
            raise sc.CommandFailed(args, "not yet")
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
        return self.health


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
        "# SC_HTTP_PORT=80\n"
        "# SC_HTTPS_PORT=443\n"
        "# SC_EMBEDDING_MODEL=BAAI/bge-m3\n"
    )
    (directory / "sc").write_text("#!/usr/bin/env python3\n")
    return directory


@pytest.fixture
def host() -> FakeHost:
    return FakeHost()

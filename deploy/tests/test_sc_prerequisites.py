from pathlib import Path

import pytest
from conftest import FakeHost, bundle, sc


def problems(host: FakeHost, tmp_path: Path) -> list[str]:
    return sc.prerequisite_problems(
        host, bundle(tmp_path / "bundle"), tmp_path / "opt" / "support-chatbot", ports=(80, 443)
    )


def test_a_ready_host_has_no_problems(host: FakeHost, tmp_path: Path) -> None:
    assert problems(host, tmp_path) == []


@pytest.mark.parametrize(
    ("host", "named"),
    [
        (FakeHost(root=False), "sudo"),
        (FakeHost(python=(3, 9)), "Python 3.10"),
        (FakeHost(docker=None), "Docker"),
        (FakeHost(compose=None), "Docker Compose"),
        (FakeHost(compose="2.21.0"), "Docker Compose 2.22"),
        (FakeHost(free_gb=12), "free disk"),
        (FakeHost(docker_root_free_gb=12), "/var/lib/docker"),
        (FakeHost(docker_group=False), "docker group"),
        (FakeHost(busy_ports={443}), "port 443"),
        # /etc/cron.d alone proves nothing: e2fsprogs ships a file there.
        (FakeHost(cron=False), "cron is not installed"),
    ],
)
def test_each_missing_prerequisite_is_named_plainly(
    host: FakeHost, named: str, tmp_path: Path
) -> None:
    found = problems(host, tmp_path)

    assert len(found) == 1
    assert named in found[0]


def test_an_incomplete_bundle_is_named(host: FakeHost, tmp_path: Path) -> None:
    unpacked = bundle(tmp_path / "bundle")
    (unpacked / "Caddyfile").unlink()

    found = sc.prerequisite_problems(host, unpacked, tmp_path / "opt", ports=(80, 443))

    assert found == ["The bundle is missing Caddyfile: unpack the whole release archive."]

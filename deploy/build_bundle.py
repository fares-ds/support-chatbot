"""Builds the install bundle for one release (OPS-1, ADR-0027).

`python3 deploy/build_bundle.py 1.4.0 dist/ [--upgrades-from 1.3.0]` writes
dist/support-chatbot-1.4.0.tar.gz and its SHA-256 checksum. --upgrades-from records the release
the upgrade test started from, which sc upgrade accepts upgrading from (ADR-0034). Standard
library only, like the server CLI (ADR-0029).
"""

import gzip
import hashlib
import io
import re
import sys
import tarfile
from pathlib import Path

BUNDLED = ("compose.yaml", "Caddyfile", "env.template", "README.md", "sc")
"""What the vendor copies to a server, with sc, the server CLI (ADR-0029)."""
EXECUTABLE = frozenset({"sc"})
_RELEASE = re.compile(r"^\d+\.\d+\.\d+$")

_VERSION_VARIABLE = re.compile(r"\$\{SC_VERSION(?::?[?-][^}]*)?\}")


def pin(compose: str, version: str) -> str:
    """The Compose file with our images pinned to the release."""
    return _VERSION_VARIABLE.sub(version, compose)


OURS = "ghcr.io/fares-ds/"
_IMAGE = re.compile(r"^\s*image:\s*(.+?)\s*$", re.MULTILINE)
_DEFAULT = re.compile(r"^\$\{\w+:-([^}]+)\}$")
_MOVING = frozenset({"latest", "stable", "main", "edge", "nightly"})


def unpinned_images(compose: str, version: str) -> list[str]:
    """Each image that is not pinned: ours must carry the release's version, and every other one
    a fixed tag or a digest. A tag may be a variable whose default is a fixed tag, so a server
    can choose another architecture's image (ADR-0028)."""
    problems = []
    for image in _IMAGE.findall(compose):
        if "@sha256:" in image:
            continue
        name, tag = _split(image)
        default = _DEFAULT.match(tag)
        if default:
            tag = default.group(1)
        if name.startswith(OURS):
            fixed = tag == version
        else:
            fixed = bool(tag) and tag not in _MOVING and any(c.isdigit() for c in tag)
        if not fixed:
            problems.append(f"{image} is not pinned")
    return problems


def _split(image: str) -> tuple[str, str]:
    """The name and the tag: the tag follows the first colon of the last path segment."""
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return image, ""
    colon = len(image) - len(last) + last.index(":")
    return image[:colon], image[colon + 1 :]


_SETTING = re.compile(r"\$\{(SC_[A-Z0-9_]+)")
_TEMPLATE_LINE = re.compile(r"^#?\s*(SC_[A-Z0-9_]+)=", re.MULTILINE)


def missing_from_template(compose: str, template: str) -> list[str]:
    """Settings the Compose file reads that the environment template does not list, set or
    commented out. SC_VERSION is not one: the bundle pins it."""
    read = set(_SETTING.findall(compose)) - {"SC_VERSION"}
    listed = set(_TEMPLATE_LINE.findall(template))
    return sorted(read - listed)


def build(version: str, deploy: Path, out: Path, *, upgrades_from: str = "") -> Path:
    """Writes out/support-chatbot-<version>.tar.gz and its .sha256, and returns the archive.
    Refuses a version that is not X.Y.Z, an unpinned image, a setting the environment template
    does not list, and a release to upgrade from that is not older."""
    if not _RELEASE.match(version):
        raise ValueError(f"{version!r} is not a release version: use X.Y.Z, such as 1.4.0")
    if upgrades_from and not (
        _RELEASE.match(upgrades_from) and _numbers(upgrades_from) < _numbers(version)
    ):
        raise ValueError(f"{upgrades_from!r} is not a release older than {version}")
    compose = pin((deploy / "compose.yaml").read_text(encoding="utf-8"), version)
    problems = unpinned_images(compose, version)
    template = (deploy / "env.template").read_text(encoding="utf-8")
    problems += [
        f"{name} is read by compose.yaml but missing from env.template"
        for name in missing_from_template(compose, template)
    ]
    if problems:
        raise ValueError("; ".join(problems))

    name = f"support-chatbot-{version}"
    files = {
        file: compose.encode() if file == "compose.yaml" else (deploy / file).read_bytes()
        for file in BUNDLED
    }
    files["release.txt"] = f"version={version}\nupgrades_from={upgrades_from}\n".encode()
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{name}.tar.gz"
    archive.write_bytes(_tarball(name, files))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n")
    return archive


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _tarball(directory: str, files: dict[str, bytes]) -> bytes:
    """The same bytes for the same files: fixed times, owners and order."""
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        tar.addfile(_entry(directory, tarfile.DIRTYPE, 0o755))
        for file in sorted(files):
            data = files[file]
            mode = 0o755 if file in EXECUTABLE else 0o644
            info = _entry(f"{directory}/{file}", tarfile.REGTYPE, mode)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _entry(name: str, kind: bytes, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type, info.mode, info.mtime = kind, mode, 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def main(arguments: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="build_bundle.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="the release, X.Y.Z")
    parser.add_argument("out_dir", type=Path, help="where to write the archive and its checksum")
    parser.add_argument(
        "--upgrades-from",
        default="",
        metavar="X.Y.Z",
        help="the release the upgrade test started from; empty for a first release",
    )
    parsed = parser.parse_args(arguments)
    try:
        archive = build(
            parsed.version,
            Path(__file__).resolve().parent,
            parsed.out_dir,
            upgrades_from=parsed.upgrades_from,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

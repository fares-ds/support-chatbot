import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from upgrade_test import previous_release, seeds

TAGS = ["v0.1.0", "v0.2.0", "v0.10.0", "v0.9.3"]


def test_a_pull_request_upgrades_from_the_newest_release() -> None:
    # 0.10.0 is newer than 0.9.3, though it sorts first as text.
    assert previous_release(TAGS, building=None) == "0.10.0"


def test_a_release_upgrades_from_the_one_before_it() -> None:
    assert previous_release(TAGS, building="v0.10.0") == "0.9.3"


@pytest.mark.parametrize(("tags", "building"), [([], None), (["v0.1.0"], "v0.1.0")])
def test_the_first_release_has_none_to_upgrade_from(tags: list[str], building: str | None) -> None:
    assert previous_release(tags, building=building) is None


def test_only_release_tags_count() -> None:
    tags = ["v0.1.0", "v0.2.0-rc1", "bench-2026-10", "0.3.0", "v0.2"]

    assert previous_release(tags, building=None) == "0.1.0"


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    for name in ("0002.sql", "0010.sql", "0005.sql", "README.md"):
        (tmp_path / name).write_text("-- a seed\n")
    return tmp_path


def names(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


def test_the_previous_release_gets_the_seeds_up_to_its_revision(seed_dir: Path) -> None:
    assert names(seeds(seed_dir, after=None, through="0005")) == ["0002.sql", "0005.sql"]


def test_the_candidate_gets_the_seeds_its_new_revisions_need(seed_dir: Path) -> None:
    # 0010 sorts after 0005 by number; README.md is not a seed.
    assert names(seeds(seed_dir, after="0005", through="0010")) == ["0010.sql"]


def test_a_revision_without_a_seed_takes_the_ones_before_it(seed_dir: Path) -> None:
    assert names(seeds(seed_dir, after=None, through="0004")) == ["0002.sql"]

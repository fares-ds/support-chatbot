import json
from pathlib import Path

import pytest

from bench.cli import main


def test_score_scores_a_saved_run_against_the_datasets_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def turn(sample: str, category: str) -> dict[str, object]:
        return {"sample": sample, "category": category, "outcome": "classified", "steps": {}}

    saved = tmp_path / "run.json"
    saved.write_text(
        json.dumps(
            {
                "name": "dev",
                "label": None,
                "started_at": "2026-10-10T12:00:00+00:00",
                "config": {"data": {"dataset": "data/acme-pay"}},
                "levels": [
                    {
                        "concurrency": 1,
                        "turns": [
                            turn("ar-person-01", "human_request"),
                            turn("darija-latin-person-01", "smalltalk"),
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["score", str(saved)]) == 0

    printed = capsys.readouterr().out
    assert printed.startswith("# Scores: dev, 2026-10-10 12:00")
    assert "| Requests for a person detected | 100.0% (1/1) | 0.0% (0/1) | 50.0% (1/2) |" in printed

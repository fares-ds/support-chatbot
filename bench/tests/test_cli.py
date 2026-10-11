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
                "budgets": {"sources": 2500},
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


def test_judge_leaves_a_run_unchanged_when_the_judge_fails_on_every_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bench import judge
    from bench.data import load_dataset
    from bench.run import knowledge_base

    model = "intfloat/multilingual-e5-small"
    _, fingerprint = knowledge_base(load_dataset(Path("data/acme-pay")).documents, model)
    saved = tmp_path / "run.json"
    text = json.dumps(
        {
            "name": "dev",
            "label": None,
            "started_at": "2026-10-11T12:00:00+00:00",
            "stops_after": None,
            "config": {"data": {"dataset": "data/acme-pay"}},
            "models": {"embedding": model},
            "knowledge_base": {"fingerprint": fingerprint},
            "services": {"ollama_url": "http://ollama:11434"},
            "levels": [
                {
                    "concurrency": 1,
                    "turns": [
                        {
                            "sample": "ar-create-age",
                            "category": "on_topic",
                            "outcome": "answered",
                            "answer": "لا [1].",
                            "prompt_chunks": [{"chunk": 1, "document": "ar-compte.md"}],
                        }
                    ],
                }
            ],
        }
    )
    saved.write_text(text, encoding="utf-8")

    def failing(settings: object) -> judge.Complete:
        async def complete(messages: list[dict[str, str]]) -> str:
            raise ConnectionError("the cloud is down")

        return complete

    monkeypatch.setattr(judge, "model_complete", failing)

    with pytest.raises(SystemExit, match="failed on every answer"):
        main(["judge", str(saved)])

    assert saved.read_text(encoding="utf-8") == text

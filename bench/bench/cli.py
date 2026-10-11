"""The command line: `python -m bench run`, `score` and `compare`."""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from bench.config import load_config
from bench.data import load_dataset
from bench.report import compare_markdown, scores_markdown
from bench.score import scores


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bench",
        description="Times Support Chatbot's AI pipeline against a running stack (#12).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="benchmark one model configuration")
    run.add_argument("config", type=Path, help="a configuration, such as configs/dev.toml")
    run.add_argument(
        "--concurrency",
        type=_levels,
        help="concurrency levels, such as 1 or 1,2,4 (default: the configuration's)",
    )
    run.add_argument(
        "--dataset",
        type=Path,
        help="a business's directory in data/, such as data/gov-uk (default: the configuration's)",
    )
    run.add_argument(
        "--turns",
        type=int,
        help="turns per level (default: the configuration's, or every sample with --classify-only)",
    )
    run.add_argument("--warmup", type=int, help="warm-up turns (default: the configuration's)")
    run.add_argument("--label", help="added to the results' name, such as vps-4gb")
    run.add_argument("--out", type=Path, default=Path("results"), help="default: results/")
    run.add_argument(
        "--classify-only",
        action="store_true",
        help="stop each turn after Gate 1, for the classifier bake-off (#14)",
    )

    score = commands.add_parser(
        "score", help="score a saved run against the dataset's current labels"
    )
    score.add_argument("results", type=Path, help="a results file (.json)")
    score.add_argument(
        "--dataset", type=Path, help="the business's directory in data/ (default: the run's)"
    )

    compare = commands.add_parser("compare", help="put saved runs side by side")
    compare.add_argument("results", type=Path, nargs="+", help="results files (.json)")

    arguments = parser.parse_args(argv)
    if arguments.command == "compare":
        runs = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.results]
        print(compare_markdown(runs), end="")
        return 0
    if arguments.command == "score":
        results = json.loads(arguments.results.read_text(encoding="utf-8"))
        dataset = load_dataset(arguments.dataset or Path(results["config"]["data"]["dataset"]))
        rescored = results | {"scores": scores(results["levels"], dataset.samples)}
        print(scores_markdown(rescored), end="")
        return 0

    _quiet_libraries()
    from bench.run import benchmark  # imports LiteLLM and DSPy, which take a few seconds

    config = load_config(arguments.config)
    if arguments.dataset:
        config = config.with_dataset(arguments.dataset)
    path = asyncio.run(
        benchmark(
            config,
            concurrency=arguments.concurrency or config.run.concurrency,
            turns=arguments.turns or (None if arguments.classify_only else config.run.turns),
            warmup=config.run.warmup if arguments.warmup is None else arguments.warmup,
            label=arguments.label,
            out=arguments.out,
            classify_only=arguments.classify_only,
        )
    )
    print(path.with_suffix(".md").read_text(encoding="utf-8"), end="")
    print(f"\nResults: {path}\nSummary: {path.with_suffix('.md')}", file=sys.stderr)
    return 0


def _levels(text: str) -> list[int]:
    try:
        levels = [int(part) for part in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("use whole numbers, such as 1,2,4") from None
    if any(level < 1 for level in levels):
        raise argparse.ArgumentTypeError("each level is 1 or more")
    return levels


def _quiet_libraries() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    for name in ("httpx", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "dspy"):
        logging.getLogger(name).setLevel(logging.WARNING)

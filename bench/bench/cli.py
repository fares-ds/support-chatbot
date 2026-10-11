"""The command line: `python -m bench run`, `judge`, `score` and `compare`."""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bench.config import load_config
from bench.data import SAMPLE_SETS, load_dataset
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
        help="turns per level (default: the configuration's, or every sample with --classify-only"
        " or --retrieve-only)",
    )
    run.add_argument("--warmup", type=int, help="warm-up turns (default: the configuration's)")
    run.add_argument("--label", help="added to the results' name, such as vps-4gb")
    run.add_argument("--out", type=Path, default=Path("results"), help="default: results/")
    run.add_argument(
        "--samples",
        choices=SAMPLE_SETS,
        default="all",
        help="which samples run: answerable ones are all recall@5 scores (default: all)",
    )
    stop = run.add_mutually_exclusive_group()
    stop.add_argument(
        "--classify-only",
        action="store_const",
        const="classify",
        dest="stops_after",
        help="stop each turn after Gate 1, for the classifier bake-off (#14)",
    )
    stop.add_argument(
        "--retrieve-only",
        action="store_const",
        const="rerank",
        dest="stops_after",
        help="stop each turn after the rerank, for the retrieval bake-off (#15)",
    )

    judge = commands.add_parser("judge", help="judge a saved run's answers, and score them (#15)")
    judge.add_argument("results", type=Path, help="a results file (.json) of a run that answered")
    judge.add_argument("--judge", help="a LiteLLM model (default: gpt-oss:120b on Ollama's cloud)")
    judge.add_argument(
        "--api-base",
        help="where the judge is served (default: the run's Ollama, for Ollama models)",
    )
    judge.add_argument(
        "--reasoning-effort", default="medium", help="the judge's (default: %(default)s)"
    )
    judge.add_argument(
        "--concurrency", type=int, default=4, help="answers judged at once (default: 4)"
    )
    judge.add_argument(
        "--dataset", type=Path, help="the business's directory in data/ (default: the run's)"
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
        # Results from before #15 recorded no retrieved chunks, so only Gate 1 scores again.
        turns = [turn for level in results["levels"] for turn in level["turns"]]
        recorded = any("retrieved" in turn for turn in turns)
        stops_after = results.get("stops_after") if recorded else "classify"
        judged = (results.get("judgments") or {}).get("turns")
        rescored = results | {
            "scores": scores(
                results["levels"], dataset.samples, stops_after=stops_after, judgments=judged
            )
        }
        print(scores_markdown(rescored), end="")
        return 0

    _quiet_libraries()
    if arguments.command == "judge":
        return _judge(arguments)
    from bench.run import benchmark  # imports LiteLLM and DSPy, which take a few seconds

    config = load_config(arguments.config)
    if arguments.dataset:
        config = config.with_dataset(arguments.dataset)
    path = asyncio.run(
        benchmark(
            config,
            concurrency=arguments.concurrency or config.run.concurrency,
            turns=arguments.turns or (None if arguments.stops_after else config.run.turns),
            warmup=config.run.warmup if arguments.warmup is None else arguments.warmup,
            label=arguments.label,
            out=arguments.out,
            stops_after=arguments.stops_after,
            samples=arguments.samples,
        )
    )
    print(path.with_suffix(".md").read_text(encoding="utf-8"), end="")
    print(f"\nResults: {path}\nSummary: {path.with_suffix('.md')}", file=sys.stderr)
    return 0


def _judge(arguments: argparse.Namespace) -> int:
    """Judges a run's answers, writes the verdicts and the scores into its results and summary,
    and prints the scores."""
    from bench.judge import JUDGE, judge_run, model_complete
    from bench.llm import ModelSettings
    from bench.run import knowledge_base, write_results
    from bench.store import chunk_ids

    path: Path = arguments.results
    results: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if results.get("stops_after"):
        raise SystemExit(f"{path} stops after {results['stops_after']}: it has no answers to judge")
    turns = [turn for level in results["levels"] for turn in level["turns"]]
    if not any("prompt_chunks" in turn for turn in turns):
        raise SystemExit(f"{path} is from before #15: it does not record its prompts' chunks")
    dataset = load_dataset(arguments.dataset or Path(results["config"]["data"]["dataset"]))
    chunks, fingerprint = knowledge_base(dataset.documents, results["models"]["embedding"])
    if fingerprint != results["knowledge_base"]["fingerprint"]:
        raise SystemExit(
            f"{dataset.name}'s knowledge base has changed since this run, so the judge would "
            "not see the sources the answer model saw"
        )
    model = arguments.judge or JUDGE
    ollama = model.startswith("ollama")
    settings = ModelSettings(
        model,
        arguments.api_base or (results["services"]["ollama_url"] if ollama else None),
        16384 if ollama else None,  # a prompt of about 4,000 tokens, and the judge's reasoning
        arguments.reasoning_effort,
        0.0,
    )
    judgments, failed = asyncio.run(
        judge_run(
            results["levels"],
            dataset.samples,
            chunk_ids(chunks),
            dataset.business,
            model_complete(settings),
            concurrency=arguments.concurrency,
        )
    )
    if failed and not judgments:
        first = next(iter(failed.values()))
        raise SystemExit(f"The judge failed on every answer, so {path} is unchanged: {first}")
    results["judgments"] = {
        "judge": model,
        "reasoning_effort": arguments.reasoning_effort,
        "judged_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "turns": judgments,
        "failed": failed,
    }
    results["scores"] = scores(
        results["levels"], dataset.samples, stops_after=None, judgments=judgments
    )
    write_results(path, results)
    print(scores_markdown(results), end="")
    print(f"\nJudged {len(judgments)} answers; failed on {len(failed)}.", file=sys.stderr)
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

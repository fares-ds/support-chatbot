"""A benchmark run: prepare the stack, warm up, run each concurrency level, write the results."""

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from collections.abc import Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from bench import METHOD_VERSION
from bench.classify import EmbeddingCheck
from bench.config import Config
from bench.data import Sample, load_documents, load_examples, load_turns
from bench.kb import Chunk, chunk_markdown
from bench.llm import ModelClassifier, ModelSettings, calibrate, prompt_tokens
from bench.pipeline import Pipeline, PromptCosts
from bench.prompts import PROMPT_VERSION, Budgets, Message, answer_prompt
from bench.records import TurnRecord
from bench.report import level_stats, summary_markdown
from bench.resources import ResourceTracker, cpu_nanoseconds, memory_bytes
from bench.runner import run_level
from bench.services import Container, Docker, Tei, ollama_info
from bench.store import KnowledgeStore, connect
from bench.tokens import TokenEstimator, calibration_texts

logger = logging.getLogger("bench")

CHUNKING = TokenEstimator({"en": 4.0, "fr": 3.5, "ar": 3.0})
"""Chunk sizes are the knowledge base's own, whatever model answers, so chunking uses fixed
estimates rather than a model's calibration."""

EMBEDDING_PREFIXES = {"e5": ("query: ", "passage: ")}
"""What a model family expects before queries and documents, matched in its name."""

SAMPLE_INTERVAL = 0.5
"""Seconds between memory and CPU samples."""


class Sampler:
    """Samples every container's memory and CPU while a level runs."""

    def __init__(self, docker: Docker, containers: Sequence[Container]) -> None:
        self._docker = docker
        self._containers = containers
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.tracker = ResourceTracker()

    async def __aenter__(self) -> Self:
        await self.sample()
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._task:
            await self._task
        await self.sample()

    async def sample(self) -> None:
        at = time.perf_counter()
        results = await asyncio.gather(
            *(self._docker.stats(container) for container in self._containers),
            return_exceptions=True,
        )
        memory, cpu = {}, {}
        for container, stats in zip(self._containers, results, strict=True):
            if isinstance(stats, BaseException):
                continue
            if (used := memory_bytes(stats)) is not None:
                memory[container.name] = used
            if (nanoseconds := cpu_nanoseconds(stats)) is not None:
                cpu[container.name] = nanoseconds
        self.tracker.add(at, memory=memory, cpu=cpu)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), SAMPLE_INTERVAL)
            except TimeoutError:
                await self.sample()


async def benchmark(
    config: Config,
    *,
    concurrency: Sequence[int],
    turns: int,
    warmup: int,
    label: str | None,
    out: Path,
) -> Path:
    """Runs the benchmark and returns the results file. The summary sits next to it."""
    started_at = datetime.now(UTC)
    async with AsyncExitStack() as resources:
        docker = Docker()
        resources.push_async_callback(docker.aclose)
        host = await docker.info()
        containers = await docker.containers(config.stack.project, config.stack.extra_containers)
        if not containers:
            raise RuntimeError(f"no running containers in Compose project {config.stack.project}")
        stack = await stack_settings(docker, containers)
        store = KnowledgeStore(
            await connect(
                host=stack["postgres_host"],
                user=stack["postgres_user"],
                password=stack["postgres_password"],
                product_database=stack["postgres_db"],
            )
        )
        resources.push_async_callback(store.aclose)
        http = await resources.enter_async_context(httpx.AsyncClient())
        results = await _run(
            config,
            http=http,
            docker=docker,
            containers=containers,
            stack=stack,
            store=store,
            concurrency=concurrency,
            turns=turns,
            warmup=warmup,
            header={
                "name": config.name,
                "label": label,
                "started_at": started_at.isoformat(timespec="seconds"),
                "method_version": METHOD_VERSION,
                "prompt_version": PROMPT_VERSION,
                "host": {
                    "cpus": host["NCPU"],
                    "memory_bytes": host["MemTotal"],
                    "architecture": host["Architecture"],
                    "os": host["OperatingSystem"],
                    "kernel": host["KernelVersion"],
                },
                "config": config.model_dump(mode="json"),
                "budgets": asdict(config.budgets),
            },
            save=lambda results: _save(results, out, started_at, config.name, label),
        )
    return _save(results, out, started_at, config.name, label)


async def _run(
    config: Config,
    *,
    http: httpx.AsyncClient,
    docker: Docker,
    containers: Sequence[Container],
    stack: dict[str, str],
    store: KnowledgeStore,
    concurrency: Sequence[int],
    turns: int,
    warmup: int,
    header: dict[str, Any],
    save: Callable[[dict[str, Any]], Path],
) -> dict[str, Any]:
    embedder = Tei(http, stack["tei_embed_url"])
    reranker = Tei(http, stack["tei_rerank_url"])
    embed_info, rerank_info = await embedder.info(), await reranker.info()
    query_prefix, document_prefix = _prefixes(embed_info["model_id"])

    data = config.data
    conversation = load_turns(data.turns)
    samples = _interleaved(conversation.samples)
    documents = load_documents(data.kb)
    chunks = [
        chunk
        for document in documents
        for chunk in chunk_markdown(
            document.markdown, language=document.language, estimator=CHUNKING
        )
    ]
    fingerprint = _fingerprint(embed_info["model_id"], document_prefix, chunks)
    if await store.loaded_fingerprint() != fingerprint:
        logger.info(
            "Loading the knowledge base: %d chunks from %d documents", len(chunks), len(documents)
        )
        started = time.perf_counter()
        await store.load(
            chunks,
            embed=lambda texts: embedder.embed([document_prefix + text for text in texts]),
            model=embed_info["model_id"],
            fingerprint=fingerprint,
        )
        logger.info("Loaded in %.1f s", time.perf_counter() - started)

    async def embed_query(texts: Sequence[str]) -> list[list[float]]:
        return await embedder.embed([query_prefix + text for text in texts])

    budgets = config.budgets
    answer = _settings(
        config.answer.model,
        config.answer.api_base,
        config.answer.reasoning_effort,
        config.answer.temperature,
        stack,
    )
    classifier_settings = (
        _settings(
            config.classifier.model,
            config.classifier.api_base,
            config.classifier.reasoning_effort,
            0.0,
            stack,
        )
        if config.classifier.mode == "model" and config.classifier.model
        else None
    )
    answer, classifier_settings = _context_windows(answer, classifier_settings, budgets)

    logger.info("Measuring how the models count tokens")
    texts = _calibration_texts(chunks, conversation.samples)
    answer_estimator = await calibrate(answer, texts)
    skeleton = answer_prompt(
        business=conversation.business,
        sources=[],
        history=[],
        message="",
        language="en",
        filler=[],
        budgets=budgets,
        estimator=answer_estimator,
        fixed_tokens=0,
    )
    answer_fixed = await prompt_tokens(answer, skeleton.messages)
    classifier: ModelClassifier | EmbeddingCheck
    if classifier_settings:
        model_classifier = ModelClassifier(classifier_settings, max_tokens=budgets.classify_out)
        classify_estimator = (
            answer_estimator
            if classifier_settings.model == answer.model
            else await calibrate(classifier_settings, texts)
        )
        empty = {
            "business_description": conversation.business.description,
            "history": "",
            "message": "",
        }
        classify_fixed = await prompt_tokens(classifier_settings, model_classifier.messages(empty))
        classifier = model_classifier
    else:
        examples, yes = load_examples(data.examples)
        classifier = await EmbeddingCheck.build(
            examples, yes=yes, embed=embed_query, margin=config.classifier.margin
        )
        classify_estimator, classify_fixed = answer_estimator, 0

    pools = _filler_pools(conversation.samples, chunks)
    pipeline = Pipeline(
        business=conversation.business,
        budgets=budgets,
        classifier=classifier,
        embed_query=embed_query,
        store=store,
        reranker=reranker,
        answer=answer,
        costs=PromptCosts(classify_fixed, classify_estimator, answer_fixed, answer_estimator),
        filler=lambda sample: _rotated(pools.get(sample.language, []), sample),
    )

    idle = Sampler(docker, containers)
    await idle.sample()
    results: dict[str, Any] = {
        **header,
        "models": {
            "classifier": (
                f"{classifier_settings.model} (DSPy)"
                if classifier_settings
                else f"embedding check on {embed_info['model_id']}"
            ),
            "answer": answer.model,
            "embedding": embed_info["model_id"],
            "reranker": rerank_info["model_id"],
        },
        "services": {
            "tei_embed": embed_info,
            "tei_rerank": rerank_info,
            "ollama_url": stack["ollama_url"],
            "num_ctx": {
                "classifier": classifier_settings.num_ctx if classifier_settings else None,
                "answer": answer.num_ctx,
            },
        },
        "calibration": {
            "answer": {
                "fixed_tokens": answer_fixed,
                "chars_per_token": dict(answer_estimator.chars_per_token),
            },
            "classifier": {
                "fixed_tokens": classify_fixed,
                "chars_per_token": dict(classify_estimator.chars_per_token),
            },
        },
        "knowledge_base": {
            "documents": len(documents),
            "chunks": len(chunks),
            "fingerprint": fingerprint,
        },
        "idle": {"memory": idle.tracker.memory_peak},
        "levels": [],
    }

    if warmup:
        logger.info("Warming up: %d turns", warmup)
        warm = await run_level(pipeline.run, samples, concurrency=1, turns=warmup)
        for record in warm:
            if record.error:
                logger.warning("Warm-up turn %s failed: %s", record.sample, record.error)
    if stack["ollama_url"]:
        try:
            results["services"]["ollama"] = await ollama_info(http, stack["ollama_url"])
        except httpx.HTTPError as error:
            logger.warning("Ollama's details are unavailable: %s", error)

    for level in concurrency:
        logger.info("Concurrency %d: %d turns", level, turns)
        pipeline.origin = time.perf_counter()
        async with Sampler(docker, containers) as sampler:
            started = time.perf_counter()
            records = await run_level(pipeline.run, samples, concurrency=level, turns=turns)
            duration = time.perf_counter() - started
        _log_errors(records)
        tracker = sampler.tracker
        results["levels"].append(
            {
                "concurrency": level,
                "duration": duration,
                "stats": level_stats(records),
                "resources": {
                    "memory_peak": tracker.memory_peak,
                    "total_memory_peak": tracker.total_memory_peak,
                    "cpu_mean": tracker.cpu_mean,
                    "cpu_peak": tracker.cpu_peak,
                },
                "turns": [asdict(record) for record in records],
            }
        )
        save(results)  # a failed later level keeps the earlier ones
    return results


async def stack_settings(docker: Docker, containers: Sequence[Container]) -> dict[str, str]:
    """Where the services are, and the Postgres password: as the stack's api container sees
    them, unless this container's environment says otherwise."""
    api = next((container for container in containers if container.name == "api"), None)
    seen = await docker.environment(api) if api else {}

    def setting(name: str, default: str) -> str:
        return os.environ.get(name) or seen.get(name) or default

    password = setting("SC_POSTGRES_PASSWORD", "")
    if not password:
        raise RuntimeError("set SC_POSTGRES_PASSWORD, or start the stack's api container")
    return {
        "postgres_host": setting("SC_POSTGRES_HOST", "postgres"),
        "postgres_user": setting("SC_POSTGRES_USER", "sc"),
        "postgres_password": password,
        "postgres_db": setting("SC_POSTGRES_DB", "support_chatbot"),
        "tei_embed_url": setting("SC_TEI_EMBED_URL", "http://tei-embed"),
        "tei_rerank_url": setting("SC_TEI_RERANK_URL", "http://tei-rerank"),
        "ollama_url": setting("SC_OLLAMA_URL", "http://ollama:11434"),
    }


def _settings(
    model: str,
    api_base: str | None,
    reasoning_effort: str | None,
    temperature: float,
    stack: dict[str, str],
) -> ModelSettings:
    if api_base is None and model.startswith("ollama"):
        api_base = stack["ollama_url"]
    return ModelSettings(model, api_base, None, reasoning_effort, temperature)


def _context_windows(
    answer: ModelSettings, classifier: ModelSettings | None, budgets: Budgets
) -> tuple[ModelSettings, ModelSettings | None]:
    """Ollama's context window for each model, large enough for its prompts and replies with a
    tenth to spare. A model that classifies and answers gets one size for both, since Ollama
    reloads a model when the size changes. Other providers ignore it."""

    def window(tokens: int) -> int:
        return math.ceil(tokens * 1.1 / 512) * 512

    answer_window = window(budgets.answer_in + budgets.answer_out)
    if classifier is None:
        return _with_window(answer, answer_window), None
    classify_window = window(budgets.classify_in + budgets.classify_out)
    if classifier.model == answer.model:
        classify_window = answer_window = max(answer_window, classify_window)
    return _with_window(answer, answer_window), _with_window(classifier, classify_window)


def _with_window(settings: ModelSettings, num_ctx: int) -> ModelSettings:
    if not settings.model.startswith("ollama"):
        return settings
    return ModelSettings(
        settings.model, settings.api_base, num_ctx, settings.reasoning_effort, settings.temperature
    )


def _prefixes(model_id: str) -> tuple[str, str]:
    for family, prefixes in EMBEDDING_PREFIXES.items():
        if family in model_id.lower():
            return prefixes
    return "", ""


def _fingerprint(model: str, document_prefix: str, chunks: Sequence[Chunk]) -> str:
    digest = hashlib.sha256(f"{model}\n{document_prefix}\n".encode())
    for chunk in chunks:
        digest.update(chunk.text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _calibration_texts(chunks: Sequence[Chunk], samples: Sequence[Sample]) -> dict[str, str]:
    """The run's own text for each class, or a stand-in for a class it has none of."""
    texts = calibration_texts(
        [*((c.text, c.language) for c in chunks), *((s.message, s.language) for s in samples)]
    )
    return {name: texts.get(name) or fallback for name, fallback in _FALLBACK.items()}


_FALLBACK = {
    "en": "How do I change my plan? You can change it at any time in your account settings. " * 25,
    "fr": "Comment changer de forfait ? Vous pouvez le changer à tout moment dans votre espace. "
    * 25,
    "ar": "كيف أغير اشتراكي؟ يمكنك تغييره في أي وقت من إعدادات حسابك. " * 30,
}


def _interleaved(samples: Sequence[Sample]) -> list[Sample]:
    """One sample per language in turn, so that even a short level sees every language."""
    by_language: dict[str, list[Sample]] = {}
    for sample in samples:
        by_language.setdefault(sample.language, []).append(sample)
    rounds = max(len(group) for group in by_language.values())
    return [group[n] for n in range(rounds) for group in by_language.values() if n < len(group)]


def _filler_pools(samples: Sequence[Sample], chunks: Sequence[Chunk]) -> dict[str, list[Message]]:
    """Earlier exchanges to fill histories with, per language: other customers' questions, and
    answers made of the knowledge base's text, as an AI assistant's answers would be."""
    pools = {}
    for language in {sample.language for sample in samples}:
        questions = [sample.message for sample in samples if sample.language == language]
        answers = [_prose(c.text) for c in chunks if c.language == language] or [
            _prose(c.text) for c in chunks
        ]
        exchanges = max(len(questions), 8)
        pools[language] = [
            message
            for n in range(exchanges)
            for message in (
                Message("customer", questions[n % len(questions)]),
                Message("ai", answers[n % len(answers)]),
            )
        ]
    return pools


def _prose(text: str) -> str:
    """The text without its table rows. An AI assistant's replies are prose, and a table is
    denser in tokens than anything a prompt's estimate is calibrated on."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("|"))


def _rotated(pool: Sequence[Message], sample: Sample) -> list[Message]:
    """The pool from a starting exchange that depends on the sample, so turns do not share
    filler that a runtime's prefix cache could reuse; less any exchange that asks the sample's
    own question."""
    exchanges = [
        (pool[n], pool[n + 1]) for n in range(0, len(pool) - 1, 2) if pool[n].text != sample.message
    ]
    if not exchanges:
        return []
    start = int(hashlib.sha256(sample.id.encode()).hexdigest(), 16) % len(exchanges)
    return [message for pair in [*exchanges[start:], *exchanges[:start]] for message in pair]


def _log_errors(records: Sequence[TurnRecord]) -> None:
    for record in records:
        if record.error:
            logger.warning("Turn %s failed: %s", record.sample, record.error)


def _save(
    results: dict[str, Any], out: Path, started_at: datetime, name: str, label: str | None
) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    stem = started_at.strftime("%Y%m%d-%H%M%S") + f"-{name}" + (f"-{label}" if label else "")
    path = out / f"{stem}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.with_suffix(".md").write_text(summary_markdown(results), encoding="utf-8")
    return path

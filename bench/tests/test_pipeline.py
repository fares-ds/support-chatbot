from collections.abc import Sequence
from typing import Any, cast

from bench.classify import EmbeddingCheck
from bench.data import Sample
from bench.kb import Chunk
from bench.llm import ModelSettings
from bench.pipeline import Pipeline, PromptCosts
from bench.prompts import Budgets, Business
from bench.services import Tei
from bench.store import Candidate, KnowledgeStore
from bench.tokens import TokenEstimator
from tests.test_classify import AXES, EXAMPLES, YES, embedder


class Untouchable:
    """A service a classify-only turn must not use."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"a classify-only turn used {name}")


async def test_a_classify_only_turn_stops_after_gate_1() -> None:
    classifier = await EmbeddingCheck.build(EXAMPLES, yes=YES, embed=embedder(AXES))
    estimator = TokenEstimator({"en": 4.0})
    pipeline = Pipeline(
        business=Business("Acme", "Phone plans"),
        budgets=Budgets(),
        classifier=classifier,
        embed_query=cast(Any, Untouchable()),
        store=cast(KnowledgeStore, Untouchable()),
        reranker=cast(Tei, Untouchable()),
        answer=ModelSettings("ollama_chat/none", None, None, None, 0.0),
        costs=PromptCosts(0, estimator, 0, estimator),
        filler=lambda sample: [],
        chunks={},
        stops_after="classify",
    )

    record = await pipeline.run(Sample("poem", "en", "en", "Write me a poem"), worker=0)

    assert (record.category, record.outcome, record.error) == ("off_topic", "classified", None)
    assert sorted(record.steps) == ["classify", "turn"]


class Store:
    async def search(self, vector: Sequence[float], query: str) -> list[Candidate]:
        return [
            Candidate(1, "Plans", "Prices", "Plans > Prices\n\nOne", "en", 1, 1),
            Candidate(2, "Plans", "Changes", "Plans > Changes\n\nTwo", "en", 2, None),
        ]


class Reranker:
    async def rerank(self, query: str, texts: Sequence[str]) -> list[tuple[int, float]]:
        return [(1, 0.9), (0, 0.4)]  # the second candidate first


async def test_a_retrieve_only_turn_records_the_reranked_chunks_and_stops() -> None:
    classifier = await EmbeddingCheck.build(EXAMPLES, yes=YES, embed=embedder(AXES))
    estimator = TokenEstimator({"en": 4.0})
    chunks = {
        1: Chunk("Plans", ("Prices",), "One", "en", 1, "plans.md", (("Prices",),)),
        2: Chunk(
            "Plans",
            ("Changes",),
            "Two",
            "en",
            1,
            "plans.md",
            (("Changes",), ("Changes", "Mid-month")),
        ),
    }
    pipeline = Pipeline(
        business=Business("Acme", "Phone plans"),
        budgets=Budgets(),
        classifier=classifier,
        embed_query=embedder(AXES),
        store=cast(KnowledgeStore, Store()),
        reranker=cast(Tei, Reranker()),
        answer=ModelSettings("ollama_chat/none", None, None, None, 0.0),
        costs=PromptCosts(0, estimator, 0, estimator),
        filler=lambda sample: [],
        chunks=chunks,
        stops_after="rerank",
    )

    record = await pipeline.run(Sample("poem", "en", "en", "Write me a poem"), worker=0)

    assert (record.outcome, record.error) == ("retrieved", None)
    assert record.retrieved == [
        {"chunk": 2, "document": "plans.md", "sections": [["Changes"], ["Changes", "Mid-month"]]},
        {"chunk": 1, "document": "plans.md", "sections": [["Prices"]]},
    ]
    assert sorted(record.steps) == ["classify", "embed", "rerank", "search", "turn"]

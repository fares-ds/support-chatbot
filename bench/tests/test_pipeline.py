from typing import Any, cast

from bench.classify import EmbeddingCheck
from bench.data import Sample
from bench.llm import ModelSettings
from bench.pipeline import Pipeline, PromptCosts
from bench.prompts import Budgets, Business
from bench.services import Tei
from bench.store import KnowledgeStore
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
        classify_only=True,
    )

    record = await pipeline.run(Sample("poem", "en", "en", "Write me a poem"), worker=0)

    assert (record.category, record.outcome, record.error) == ("off_topic", "classified", None)
    assert sorted(record.steps) == ["classify", "turn"]

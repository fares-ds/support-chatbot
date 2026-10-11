"""One turn of the AI pipeline, step by step (Flow B): classify, embed, search, rerank, answer.

Every turn runs every step, whatever the classifier decides, so that runs compare like with
like. The turn record keeps the category and the reranker's top chunks, for the scorers. A
pipeline can stop each turn early: after Gate 1, for the classifier bake-off (#14), or after the
rerank, for the retrieval one (#15).
"""

import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Literal

from bench.answer import read_answer
from bench.classify import Classification, Embed, EmbeddingCheck
from bench.data import Sample
from bench.kb import Chunk, fuse
from bench.llm import ModelClassifier, ModelSettings, stream_answer
from bench.prompts import Budgets, Business, Message, Source, answer_prompt, classify_prompt
from bench.records import TurnRecord
from bench.services import Tei
from bench.store import Candidate, KnowledgeStore
from bench.tokens import TokenEstimator

TOP = 5
"""The reranker's top chunks a turn records, for recall@5."""

Stop = Literal["classify", "rerank"]
"""Where a turn may stop early: after Gate 1, or after the rerank."""


@dataclass(frozen=True)
class PromptCosts:
    """What each prompt costs before its variable parts, and how its model counts tokens."""

    classify_fixed: int
    classify_estimator: TokenEstimator
    answer_fixed: int
    answer_estimator: TokenEstimator


class Pipeline:
    def __init__(
        self,
        *,
        business: Business,
        budgets: Budgets,
        classifier: ModelClassifier | EmbeddingCheck,
        embed_query: Embed,
        store: KnowledgeStore,
        reranker: Tei,
        answer: ModelSettings,
        costs: PromptCosts,
        filler: Callable[[Sample], Sequence[Message]],
        chunks: Mapping[int, Chunk],
        stops_after: Stop | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """`chunks` are the knowledge base's, by the store's chunk ID."""
        self._business = business
        self._budgets = budgets
        self._classifier = classifier
        self._embed_query = embed_query
        self._store = store
        self._reranker = reranker
        self._answer = answer
        self._costs = costs
        self._filler = filler
        self._chunks = chunks
        self._stops_after = stops_after
        self._clock = clock
        self.origin = clock()
        """Turn start times count from here: the runner resets it at each level."""

    async def run(self, sample: Sample, worker: int) -> TurnRecord:
        clock = self._clock
        start = clock()
        record = TurnRecord(
            sample=sample.id,
            language=sample.language,
            worker=worker,
            started=start - self.origin,
            steps={},
            tokens={},
            tokens_per_second=None,
            category=None,
            outcome="error",
        )
        steps, tokens = record.steps, record.tokens
        step = "classify"
        try:
            began = clock()
            classification = await self._classify(sample, record)
            steps["classify"] = clock() - began
            record.category = classification.category
            query = record.search_query = classification.search_query or sample.message
            if self._stops_after == "classify":
                record.outcome = "classified"
                steps["turn"] = clock() - start
                return record

            step = "embed"
            began = clock()
            [vector] = await self._embed_query([query])
            steps["embed"] = clock() - began

            step = "search"
            began = clock()
            candidates = await self._store.search(vector, query)
            merged = fused(candidates)
            steps["search"] = clock() - began

            step = "rerank"
            began = clock()
            order = await self._reranker.rerank(query, [c.text for c in merged]) if merged else []
            steps["rerank"] = clock() - began
            ranked = [merged[index] for index, _ in order]
            record.retrieved = [self._retrieved(candidate) for candidate in ranked[:TOP]]
            if self._stops_after == "rerank":
                record.outcome = "retrieved"
                steps["turn"] = clock() - start
                return record

            step = "answer"
            prompt = answer_prompt(
                business=self._business,
                sources=[Source(c.title, c.text, c.language) for c in ranked],
                history=sample.history,
                message=sample.message,
                language=sample.language,
                filler=self._filler(sample),
                budgets=self._budgets,
                estimator=self._costs.answer_estimator,
                fixed_tokens=self._costs.answer_fixed,
            )
            record.estimated_tokens["answer_in"] = prompt.tokens
            record.prompt_chunks = [self._retrieved(c) for c in ranked[: len(prompt.sources)]]
            record.sources = [
                f"{c.title} > {c.heading_path}" if c.heading_path else c.title
                for c in ranked[: len(prompt.sources)]
            ]
            began = clock()
            async with aclosing(
                stream_answer(self._answer, prompt.messages, max_tokens=self._budgets.answer_out)
            ) as deltas:
                timing = await read_answer(deltas, started=began, clock=clock)
        except Exception as error:
            record.error = f"{step}: {type(error).__name__}: {error}"[:500]
            steps["turn"] = clock() - start
            return record

        if not timing.text:
            record.error = "answer: the model returned no text"
            steps["turn"] = clock() - start
            return record
        if timing.first_token is not None:
            steps["first_token"] = timing.first_token
        if timing.first_visible is not None:
            steps["first_visible"] = timing.first_visible
            steps["turn_first_visible"] = began - start + timing.first_visible
        steps["answer"] = timing.complete
        steps["turn"] = clock() - start
        if timing.prompt_tokens is not None:
            tokens["answer_in"] = timing.prompt_tokens
        tokens["answer_out"] = timing.tokens_out
        record.tokens_per_second = timing.tokens_per_second
        record.answer = timing.text
        record.outcome = "abstained" if timing.abstained else "answered"
        return record

    def _retrieved(self, candidate: Candidate) -> dict[str, object]:
        chunk = self._chunks[candidate.id]
        return {
            "chunk": candidate.id,
            "document": chunk.document,
            "sections": [list(section) for section in chunk.sections],
        }

    async def _classify(self, sample: Sample, record: TurnRecord) -> Classification:
        if isinstance(self._classifier, EmbeddingCheck):
            previous = [turn.text for turn in sample.history if turn.role == "customer"]
            return await self._classifier.classify(
                sample.message,
                previous_message=previous[-1] if previous else None,
                offered_person=sample.offered_person,
                interface_language=sample.interface_language,
            )
        prompt = classify_prompt(
            business=self._business,
            history=sample.history,
            message=sample.message,
            language=sample.language,
            filler=self._filler(sample),
            budgets=self._budgets,
            estimator=self._costs.classify_estimator,
            fixed_tokens=self._costs.classify_fixed,
        )
        record.estimated_tokens["classify_in"] = prompt.tokens
        classified = await self._classifier.classify(prompt.inputs)
        record.classify_retried = classified.retried
        record.tokens["classify_in"] = classified.prompt_tokens
        record.tokens["classify_out"] = classified.completion_tokens
        return classified.classification


def fused(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Gate 2's merge of the two searches by reciprocal rank fusion."""
    by_vector = sorted((c for c in candidates if c.vector_rank), key=lambda c: c.vector_rank or 0)
    by_text = sorted((c for c in candidates if c.fulltext_rank), key=lambda c: c.fulltext_rank or 0)
    by_id = {candidate.id: candidate for candidate in candidates}
    return [by_id[i] for i in fuse([[c.id for c in by_vector], [c.id for c in by_text]])]

"""Against a running stack, from the bench container:

docker compose run --rm --entrypoint pytest bench -m stack
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from bench.data import load_documents
from bench.kb import chunk_markdown
from bench.pipeline import fused
from bench.resources import memory_bytes
from bench.run import CHUNKING, stack_settings
from bench.services import Docker, Tei
from bench.store import KnowledgeStore, connect

pytestmark = pytest.mark.stack

PROJECT = "support-chatbot"


@pytest.fixture
async def docker() -> AsyncIterator[Docker]:
    client = Docker()
    yield client
    await client.aclose()


@pytest.fixture
async def stack(docker: Docker) -> dict[str, str]:
    return await stack_settings(docker, await docker.containers(PROJECT))


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def test_the_reranker_puts_the_text_that_answers_first(
    stack: dict[str, str], http: httpx.AsyncClient
) -> None:
    reranker = Tei(http, stack["tei_rerank_url"])
    texts = ["Our shops open at nine.", "Transfer credit by dialling *300*, the number, then #."]

    [(best, _), *_] = await reranker.rerank("How do I send credit to my sister?", texts)

    assert best == 1


async def test_the_knowledge_base_finds_the_chunk_that_answers(
    stack: dict[str, str], http: httpx.AsyncClient
) -> None:
    embedder = Tei(http, stack["tei_embed_url"])
    chunks = [
        chunk
        for document in load_documents(Path("data/acme-pay/kb"))
        for chunk in chunk_markdown(
            document.markdown,
            document=document.name,
            language=document.language,
            estimator=CHUNKING,
        )
    ]
    store = KnowledgeStore(
        await connect(
            host=stack["postgres_host"],
            user=stack["postgres_user"],
            password=stack["postgres_password"],
            product_database=stack["postgres_db"],
        )
    )
    # The next benchmark run sees another fingerprint, and loads the knowledge base again.
    await store.load(chunks, embed=embedder.embed, model="test", fingerprint="integration test")
    question = "Comment parrainer un proche pour recevoir 200 DA ?"
    [vector] = await embedder.embed([question])

    found = fused(await store.search(vector, question))

    assert "Parrainage" in [candidate.title for candidate in found[:3]]


async def test_every_container_of_the_stack_reports_its_memory(docker: Docker) -> None:
    containers = await docker.containers(PROJECT)

    used = {container.name: memory_bytes(await docker.stats(container)) for container in containers}

    assert {"postgres", "tei-embed", "tei-rerank", "valkey"} <= set(used)
    assert all(value and value > 0 for value in used.values())

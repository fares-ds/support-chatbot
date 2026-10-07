"""The sample knowledge base in Postgres, stored and searched as the tech stack describes.

It lives in its own database, `bench`, so it never touches the product's tables, and
`DROP DATABASE bench` removes it.
"""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import asyncpg

from bench.kb import Chunk

DATABASE = "bench"
MODEL_ID = 1
"""The bench database holds one embedding model at a time; a new model reloads it."""

_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Candidate:
    id: int
    title: str
    heading_path: str
    text: str
    language: str
    vector_rank: int | None
    fulltext_rank: int | None


async def connect(*, host: str, user: str, password: str, product_database: str) -> asyncpg.Pool:
    """A pool on the bench database, which is created on first use."""
    admin = await asyncpg.connect(
        host=host, user=user, password=password, database=product_database
    )
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DATABASE):
            await admin.execute(f'CREATE DATABASE "{DATABASE}"')
    finally:
        await admin.close()
    # Enough connections that searches never queue for one, which would slow the search step.
    return await asyncpg.create_pool(
        host=host, user=user, password=password, database=DATABASE, min_size=1, max_size=32
    )


class KnowledgeStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._dimensions: int | None = None

    async def aclose(self) -> None:
        await self._pool.close()

    async def loaded_fingerprint(self) -> str | None:
        """What `load` last stored, or None for an empty database."""
        async with self._pool.acquire() as connection:
            if not await connection.fetchval("SELECT to_regclass('knowledge') IS NOT NULL"):
                return None
            row = await connection.fetchrow(
                "SELECT fingerprint, dimensions FROM knowledge, embedding_models"
            )
        if row is None:
            return None
        self._dimensions = row["dimensions"]
        fingerprint: str = row["fingerprint"]
        return fingerprint

    async def load(
        self,
        chunks: Sequence[Chunk],
        *,
        embed: Callable[[Sequence[str]], Awaitable[list[list[float]]]],
        model: str,
        fingerprint: str,
        batch: int = 16,
    ) -> None:
        """Replaces the knowledge base: chunks, their vectors and both indexes (KB-7)."""
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), batch):
            vectors += await embed([chunk.text for chunk in chunks[start : start + batch]])
        dimensions = len(vectors[0])
        if dimensions > 4000:
            raise ValueError("pgvector indexes halfvec up to 4,000 dimensions (KB-7)")
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(_SCHEMA)
            await connection.execute(
                "INSERT INTO embedding_models (id, name, dimensions) VALUES ($1, $2, $3)",
                MODEL_ID,
                model,
                dimensions,
            )
            await connection.executemany(
                "INSERT INTO chunks (id, title, heading_path, text, language, tokens)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                [
                    (n, c.title, " > ".join(c.heading_path), c.text, c.language, c.tokens)
                    for n, c in enumerate(chunks, 1)
                ],
            )
            await connection.executemany(
                "INSERT INTO chunk_embeddings (chunk_id, model_id, embedding)"
                " VALUES ($1, $2, $3::text::halfvec)",
                [(n, MODEL_ID, _vector(v)) for n, v in enumerate(vectors, 1)],
            )
            # One HNSW index per model, on a cast to its size and limited to its rows. Queries
            # repeat the cast and the filter, or Postgres does not use the index.
            await connection.execute(
                f"CREATE INDEX chunk_embeddings_model_{MODEL_ID} ON chunk_embeddings USING hnsw"
                f" ((embedding::halfvec({dimensions})) halfvec_cosine_ops)"
                f" WHERE model_id = {MODEL_ID}"
            )
            await connection.execute("INSERT INTO knowledge (fingerprint) VALUES ($1)", fingerprint)
        self._dimensions = dimensions

    async def search(
        self, vector: Sequence[float], query: str, *, vector_top: int = 20, fulltext_top: int = 20
    ) -> list[Candidate]:
        """Gate 2's two searches in one round trip: the nearest chunks by cosine distance, and
        the best full-text matches for any word of the query. Rank fusion happens in Python."""
        if self._dimensions is None:
            raise RuntimeError("load the knowledge base first")
        words = _WORD.findall(query.lower())
        if not words:
            words, fulltext_top = ["x"], 0  # nothing to match: skip the full-text search
        rows = await self._pool.fetch(
            _search_sql(self._dimensions),
            _vector(vector),
            vector_top,
            " | ".join(words),
            fulltext_top,
        )
        return [Candidate(**dict(row)) for row in rows]


def _vector(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.6g}" for value in values) + "]"


def _search_sql(dimensions: int) -> str:
    """Type modifiers and the index's filter cannot be parameters, so the vector size and the
    model's ID are written into the SQL. Both are integers."""
    cast = f"halfvec({dimensions:d})"
    return f"""
        WITH nearest AS (
            SELECT chunk_id, row_number() OVER (ORDER BY distance) AS rank
            FROM (
                SELECT chunk_id, embedding::{cast} <=> $1::text::{cast} AS distance
                FROM chunk_embeddings
                WHERE model_id = {MODEL_ID}
                ORDER BY embedding::{cast} <=> $1::text::{cast}
                LIMIT $2
            ) found
        ),
        matching AS (
            SELECT id AS chunk_id, row_number() OVER (ORDER BY score DESC) AS rank
            FROM (
                SELECT id, ts_rank_cd(tsv, query) AS score
                FROM chunks, to_tsquery('simple', $3) AS query
                WHERE tsv @@ query
                ORDER BY score DESC
                LIMIT $4
            ) found
        )
        SELECT c.id, c.title, c.heading_path, c.text, c.language,
               nearest.rank AS vector_rank, matching.rank AS fulltext_rank
        FROM chunks c
        LEFT JOIN nearest ON nearest.chunk_id = c.id
        LEFT JOIN matching ON matching.chunk_id = c.id
        WHERE nearest.rank IS NOT NULL OR matching.rank IS NOT NULL
    """  # noqa: S608


_SCHEMA = """
    CREATE EXTENSION IF NOT EXISTS vector;
    DROP TABLE IF EXISTS knowledge, chunk_embeddings, chunks, embedding_models;
    CREATE TABLE knowledge (fingerprint text NOT NULL, loaded_at timestamptz DEFAULT now());
    CREATE TABLE embedding_models (
        id int PRIMARY KEY,
        name text NOT NULL,
        dimensions int NOT NULL
    );
    CREATE TABLE chunks (
        id int PRIMARY KEY,
        title text NOT NULL,
        heading_path text NOT NULL,
        text text NOT NULL,
        language text NOT NULL,
        tokens int NOT NULL,
        -- The language-neutral dictionary until per-language ones arrive (KB-17).
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED
    );
    CREATE INDEX chunks_tsv ON chunks USING gin (tsv);
    CREATE TABLE chunk_embeddings (
        chunk_id int NOT NULL REFERENCES chunks,
        model_id int NOT NULL REFERENCES embedding_models,
        embedding halfvec NOT NULL,
        PRIMARY KEY (chunk_id, model_id)
    );
"""

# ADR-0024: Stack corrections after the stack review

- Status: Accepted; amended by [ADR-0028](0028-two-tei-containers.md)
- Date: 2026-10-06
- Deciders: Fares
- Amends: [ADR-0014](0014-v1-tech-stack.md)

## Context

A review of the approved stack against the libraries' own documentation found five problems that would bite during the build, six gaps where engineering would otherwise decide silently, and four simplifications. Sources:

- [pgvector](https://github.com/pgvector/pgvector): HNSW and IVFFlat index `vector` up to 2,000 dimensions and `halfvec` up to 4,000. Mixed dimensions in one column need one expression-and-partial index per dimension.
- [DSPy issue #8211](https://github.com/stanfordnlp/dspy/issues/8211): DSPy streams by spotting its own field markers in the token stream. A provider that split those markers across chunks broke streaming (since fixed).
- [Celery, Redis broker](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html): the default visibility timeout is 1 hour, and a task running longer is delivered again. Redis should not evict keys.
- [Text Embeddings Inference](https://github.com/huggingface/text-embeddings-inference): Apache-2.0, CPU image, `/embed` and `/rerank`, supports XLM-RoBERTa models.
- [trafilatura](https://github.com/adbar/trafilatura): Apache-2.0 since version 1.8.0. [restic](https://github.com/restic/restic): BSD-2-Clause, encrypted, SFTP and S3-compatible backends.
- PostgreSQL 18 has been generally available since 25 September 2025, and pgvector publishes `pgvector/pgvector:pg18` images.

## Decision

**Problems fixed**

1. **Streaming.** Answers are generated and streamed through the LiteLLM library directly. DSPy is kept for the classifier's structured output.
2. **Embeddings.** Each chunk's vector for each model is stored as `halfvec` in its own row. Each model gets its own HNSW index on `(embedding::halfvec(n))`, limited to that model's rows. Models above 4,000 dimensions are refused, and shorter vectors are requested where the provider supports them.
3. **SSRF.** Every outbound fetch for web import goes through one guarded HTTP client. It allows http and https only. It refuses addresses that resolve to private, loopback, link-local or internal-network ranges, checked before connecting and on every redirect. It caps response size and fetch time.
4. **CPU mode.** When classification would run on CPU, it uses a cheaper classifier: an embedding-similarity check against example phrases per category (on TEI), or a small model, whichever passes M0 on accuracy and speed. The answer model is then the only large model loaded. M0 times the whole pipeline end to end.
5. **Widget build.** The loader is its own plain TypeScript bundle (≤ 10 KB gzipped). The chat app inside the iframe is a small Vite and React build.

**Gaps closed**

6. **AI turns** run inside the API process as async tasks. A Valkey lock allows one turn per conversation. A turn times out after 30 seconds with an external provider; the CPU value comes from M0. On shutdown the API stops starting turns and waits up to 30 seconds for running ones; unfinished turns hand off.
7. **Schedules.** Celery Beat, inside the worker container, runs the timed jobs. The server's cron runs the daily backup, independently of the app containers.
8. **Workers** use synchronous SQLAlchemy sessions. Celery's visibility timeout is set above the longest job measured in M0. Valkey runs with eviction disabled.
9. **Sessions.** The widget authenticates with a bearer token kept in the iframe's own storage, never a cookie. The dashboard and API share one domain. Dashboard cookies are SameSite=Strict, and state-changing requests carry a CSRF token.
10. **Named components:**
    - documents: pdfplumber (PDF), python-docx (DOCX) and markdown-it-py (Markdown), with Docling as the fallback if the M0 bake-off needs better tables or headings
    - excluded: PyMuPDF, because it is AGPL
    - web pages: a crawler of our own on httpx, through the guarded client, with trafilatura extracting page text
    - backups: restic
    - images: GitHub Container Registry, private, with a read-only token per install
11. **Memory and logs.** M0 benchmarks the whole stack together on the target VPS. Container logs are capped in the Compose file.

**Simplifications adopted**

12. Text Embeddings Inference serves embeddings and reranking, replacing the custom model service.
13. No vLLM container in V1. The model settings accept any OpenAI-compatible endpoint, which covers vLLM on a GPU host.
14. Valkey replaces Redis, and Postgres 18 replaces Postgres 16.
15. The Next.js dashboard is exported as static files served by Caddy. There is no Node container.

## Consequences

- An install runs seven containers: Caddy, API, worker (with Beat), TEI, Ollama, Postgres and Valkey.
- The dashboard cannot use Next.js server features (server rendering, middleware, server actions). Its pages call the API from the browser.
- ADR-0011's "vLLM on a GPU host" becomes "any OpenAI-compatible endpoint".
- The models chosen in M0 must be confirmed to run on TEI and Ollama on the target VPS.

## Update, 2026-10-06 (final review)

The CPU classifier's fallbacks, and what happens with models nobody has calibrated, are settled in [ADR-0025](0025-cpu-classifier-fallbacks-and-uncalibrated-models.md).

## Update, 2026-10-06 (M0 planning)

A TEI container loads one model, so embeddings and reranking run in two TEI containers, and an install runs eight containers ([ADR-0028](0028-two-tei-containers.md)).

# ADR-0014: Tech stack for V1

- Status: Accepted (approved in grilling round 6); amended by [ADR-0024](0024-stack-review-corrections.md)
- Date: 2026-10-05
- Deciders: Fares

## Context

The vendor asked to take the stack from the earlier projects (`ai-support-api`, `support-agent-platform`) rather than from the architecture diagram ([ADR-0005](0005-standalone-industry-agnostic-product.md)). Constraints since then:

- one install per business, on a single VPS ([ADR-0006](0006-one-install-per-business.md))
- CPU only, with 4–7B local models ([ADR-0011](0011-cpu-first-models.md))
- built and operated by one person over server access ([ADR-0012](0012-vendor-operates-every-install.md))
- proprietary ([ADR-0010](0010-proprietary-closed-source.md))

## Proposal

| Concern | Choice | Source |
| --- | --- | --- |
| Backend and AI orchestration | FastAPI on Python 3.12, with uv, SQLAlchemy (async) and Alembic | Earlier projects |
| Dashboard and widget | Next.js, React, TypeScript, Tailwind | Earlier projects and diagram |
| Database | Postgres 16 | Earlier projects |
| Vector search | pgvector, inside Postgres | `support-agent-platform`, diagram |
| Model calls | DSPy modules, reaching every provider through the LiteLLM library; no proxy service | `ai-support-api` |
| Local model runtime | Ollama on CPU; vLLM on hosts that have a GPU | Diagram, vendor |
| Embeddings and reranking | A small CPU model service (sentence-transformers), or an external API, chosen per install | `ai-support-api`, diagram |
| Live chat delivery | FastAPI WebSockets, with Redis pub/sub between processes | Replaces Centrifugo |
| Dashboard sign-in | Built into the app: sessions, invites, password reset | Replaces Keycloak |
| File storage | A disk volume on the VPS | Replaces MinIO |
| Background jobs | Celery, with Redis as the broker | Diagram; used in `ExpertComptable` |
| Cache, broker, pub/sub | Redis, or Valkey, its BSD-licensed fork | Earlier projects |
| AI tracing and evals | One record per AI turn in Postgres, plus structured logs | Replaces Prometheus, Grafana, OpenTelemetry and Langfuse on the VPS |
| HTTPS and routing | Caddy, with automatic certificates | New |
| Deployment | Docker Compose, with images pinned by version from a private registry | Earlier projects |

## Why

- Every service shares one VPS with a 4–7B model, so each extra service takes RAM the model needs. This proposal runs eight containers: Caddy, web, API, worker, model service, Postgres, Redis and Ollama.
- One person builds and operates every install. The stack uses the languages and tools from the earlier projects.
- Neon's branching, Keycloak's identity federation and Centrifugo's fan-out solve multi-tenant and high-scale problems that V1 no longer has.

## Consequences

- The PRD's architecture section is replaced. That covers Next.js API orchestration, Kubernetes, Neon, Keycloak, Centrifugo, the LiteLLM proxy, MinIO, Prometheus and Grafana.
- Password reset needs either SMTP on each install or a reset command the vendor runs.
- Tracing beyond the turn records (Langfuse, OpenTelemetry) can be added later without changing the records.

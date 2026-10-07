# Support Chatbot

A chat bubble a business adds to its website. An AI assistant answers the business's customers from the business's own documents and web pages, and hands the conversation to a person on the business's team when it cannot answer. Each business runs its own install on its own server, installed and operated by the vendor.

Proprietary, not open source ([ADR-0010](docs/adr/0010-proprietary-closed-source.md)).

## Where things are

| Path | What |
| --- | --- |
| [docs/prd.md](docs/prd.md) | The V1 PRD, the source of truth |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [docs/tech-stack.md](docs/tech-stack.md) | The stack and its configuration rules |
| [docs/glossary.md](docs/glossary.md) | The words to use in code and screens |
| `backend/` | FastAPI API, Celery worker and Alembic migrations |
| `frontend/` | Dashboard, widget, widget loader and the generated API client |
| `deploy/` | The install bundle: Compose file, Caddyfile, environment template and server CLI |
| `compose.yaml` | The development stack: the install bundle's Compose file, with the backend built from source |
| `bench/` | The M0 benchmark |

## Development

You need Docker and [uv](https://docs.astral.sh/uv/).

- `docker compose up --build` starts the stack on https://localhost with the development values in `deploy/dev.env`. TEI runs small multilingual models in development; servers default to bge-m3 and bge-reranker-v2-m3.
- The stack's own Ollama is left out in development, because its image is about 9 GB. Either point the API at an Ollama that already runs, with a `.env` file at the repository root holding `SC_OLLAMA_URL=http://host.docker.internal:11434`, or run the stack's own with `COMPOSE_PROFILES=ollama`, as CI does.
- `curl -k https://localhost/api/health` reports each service the install runs; `/api/health/ready` reports only what the API needs to serve, Postgres and Valkey. Caddy signs `localhost` with its own certificate authority; to verify instead of passing `-k`, copy its root certificate with `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .` and pass `--cacert root.crt`.
- In `backend/`: `uv run pytest`, `uv run ruff check`, `uv run ruff format` and `uv run mypy`. CI runs the same checks, plus the stack, on every pull request.
- The M0 benchmark times the AI pipeline against the running stack: see [bench/README.md](bench/README.md).

## Workflow

One short-lived branch per issue, squash-merged into `main` by pull request once CI passes. Pull request titles follow Conventional Commits. Releases are `vX.Y.Z` tags ([ADR-0027](docs/adr/0027-repository-layout-and-git-workflow.md)).

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
| `backend/` | The FastAPI API, the Celery worker with Beat, and the Alembic migrations |
| [frontend/](frontend/) | A pnpm workspace. `api-client/` is the API's TypeScript client and the WebSocket event types, generated from the backend (ADR-0026); the dashboard, widget and widget loader join it in M1. |
| [deploy/](deploy/) | The install bundle: the Compose file, Caddyfile, environment template and `sc`, the server CLI, built into a release by `build_bundle.py`. Also the Caddy image and the development Compose files. |
| `compose.yaml` | The development stack: the install bundle's Compose file, with the backend and Caddy images built from source |
| [bench/](bench/) | The M0 benchmark harness |

## Development

You need Docker and [uv](https://docs.astral.sh/uv/).

- `docker compose up --build` starts the stack on https://localhost with the development values in `deploy/dev.env`. TEI runs small multilingual models in development; servers default to bge-m3 and bge-reranker-v2-m3.
- The stack's own Ollama is left out in development, because its image is about 9 GB. Either point the API at an Ollama that already runs, with a `.env` file at the repository root holding `SC_OLLAMA_URL=http://host.docker.internal:11434`, or run the stack's own with `COMPOSE_PROFILES=ollama`, as CI does.
- `curl -k https://localhost/api/health` reports each service the install runs, the database's schema revision and the worker's last heartbeat; `/api/health/ready` reports only what the API needs to serve, Postgres and Valkey. Caddy signs `localhost` with its own certificate authority; to verify instead of passing `-k`, copy its root certificate with `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .` and pass `--cacert root.crt`.
- In `backend/`: `uv run pytest`, `uv run ruff check`, `uv run ruff format` and `uv run mypy`. CI runs the same checks, plus the stack, on every pull request. A pull request that touches `backend/` or `deploy/` also installs a release bundle with `sc` on a fresh runner, backs it up, restores it onto a second fresh install, upgrades it to a new release and rolls back from a failed one, checks `sc status`, runs the upgrade test from the previous release, and scans the dependencies and images for vulnerabilities.
- **Schema changes** are Alembic migrations in `backend/migrations/versions/`, numbered: `uv run alembic revision --rev-id 0003 -m "Add the conversations table"` in `backend/`, with the next free number. The stack's `migrate` job applies them before the API starts; the API never migrates itself ([ADR-0013](docs/adr/0013-upgrades-and-migrations.md)).
  - A migration only adds tables, nullable columns (or ones with a server default) and indexes, so the previous release keeps working.
  - Dropping or renaming a table or column is the contract step, one release later: the migration sets `contract` to what the previous release had stopped using.
  - `downgrade()` stays empty; a rollback restores the pre-upgrade backup.
  - CI checks these rules: `uv run python -m tools.migration_rules migrations/versions`.
  - A migration that adds a table also adds its rows, in `backend/tests/upgrade_seeds/<revision>.sql`. CI's upgrade test (`deploy/upgrade_test.py`) seeds the previous release's database, upgrades it with the pull request's migrations, and checks that both releases still run on it; it fails if a table has no seed rows.
- In `frontend/`, with Node 24 and pnpm (the version in `frontend/package.json`'s `packageManager`; `corepack enable`, or `npx pnpm@<version>`): `pnpm install`, then `pnpm typecheck`.
- **The API client is generated, and committed.** After changing a route, a response model or a WebSocket event (`backend/app/events.py`), run `pnpm --dir frontend generate` and commit what changes: CI regenerates it and fails on any difference. It exports the OpenAPI spec and the events' JSON Schema from the backend, without a server, then runs Hey API's openapi-ts and json-schema-to-typescript. Operations are named after their route functions, so `def health()` becomes `health()` and `healthOptions()` in TypeScript.
- In `deploy/`: `uv run --no-project --python 3.10 --with pytest pytest` tests `sc`, the bundle builder and the upgrade test's helpers on the oldest Python `sc` supports; `uvx ruff check .` lints them.
- The M0 benchmark times the AI pipeline against the running stack, and scores it against the PRD's release gates: see [bench/README.md](bench/README.md). Its reports, such as [round 1](bench/reports/2026-10-11-bake-offs-round-1.md), are in `bench/reports/`.

## Workflow

One short-lived branch per issue, squash-merged into `main` by pull request once CI passes. CI pulls Docker Hub images logged in with the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`, a read-only access token: anonymous pulls share the runners' addresses and hit Docker Hub's rate limit. Without the secrets, it pulls anonymously. Pull request titles follow Conventional Commits. Releases are `vX.Y.Z` tags ([ADR-0027](docs/adr/0027-repository-layout-and-git-workflow.md)); [deploy/README.md](deploy/README.md) explains how to cut one, and how each install gets its pull token.

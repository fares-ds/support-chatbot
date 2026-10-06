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
| `bench/` | The M0 benchmark |

## Workflow

One short-lived branch per issue, squash-merged into `main` by pull request once CI passes. Pull request titles follow Conventional Commits. Releases are `vX.Y.Z` tags ([ADR-0027](docs/adr/0027-repository-layout-and-git-workflow.md)).

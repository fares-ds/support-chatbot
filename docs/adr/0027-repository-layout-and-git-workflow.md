# ADR-0027: Repository layout and git workflow

- Status: Accepted; refined by [ADR-0036](0036-every-pull-request-gets-a-second-review.md), which settles its open point
- Date: 2026-10-06
- Deciders: Fares

## Context

Planning left the repository undecided. V1's code has four parts that ship together under one version ([ADR-0013](0013-upgrades-and-migrations.md)):

- a Python backend: the FastAPI API, the Celery worker and the Alembic migrations ([ADR-0014](0014-v1-tech-stack.md))
- three TypeScript front ends (the dashboard, the widget chat app and the widget loader), sharing a client generated from the backend's OpenAPI spec ([ADR-0024](0024-stack-review-corrections.md), [ADR-0026](0026-typed-api-client-from-openapi.md))
- the install bundle: the Compose file, the environment template and the server CLI (OPS-1)
- the M0 benchmark

One person builds it with Claude Code. The code is proprietary ([ADR-0010](0010-proprietary-closed-source.md)) and belongs to the vendor, not to a design partner ([ADR-0005](0005-standalone-industry-agnostic-product.md)). Images go to GitHub Container Registry ([ADR-0024](0024-stack-review-corrections.md)).

## Decision

1. **One private repository,** `fares-ds/support-chatbot`, on the vendor's personal GitHub account. Its commits use the vendor's personal identity, not the OneClickDZ one.
2. **One root per toolchain:**

   | Path | Holds |
   | --- | --- |
   | `backend/` | A uv project: the FastAPI API, the Celery worker, Alembic migrations and tests. One image runs the API, the worker and the migration job. |
   | `frontend/` | A pnpm workspace: `dashboard/`, `widget/` (the chat app), `widget-loader/` and `api-client/` (generated) |
   | `deploy/` | The install bundle: Compose file, Caddyfile, environment template and server CLI |
   | `bench/` | The M0 benchmark harness |
   | `docs/` | PRD, ADRs, glossary and tech stack |
   | `.github/workflows/` | CI and releases |

3. **Trunk-based workflow.** `main` is always releasable. Each issue gets a short-lived branch, merged into `main` by a squash-merged pull request once CI passes. Pull request titles become the commit messages and follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
4. **Releases are tags.** A `vX.Y.Z` tag on `main` builds the images, pushes them to GitHub Container Registry and publishes the install bundle. The upgrade test (OPS-4) upgrades from the previous tag.

## Consequences

- ADR-0026's check, which regenerates the client and event types and fails on any difference, runs in one CI job, because the spec and the client live in one repository.
- One tag versions every image and the install bundle together. No part has its own version.
- On a free personal account, GitHub neither protects branches nor requires status checks in private repositories; that takes GitHub Pro ([GitHub's plans](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)). Until then, merging only on a green CI is a rule the vendor keeps, not one GitHub enforces.
- GitHub Free gives private repositories 2,000 Actions minutes a month. Container Registry storage and bandwidth are free for now, and GitHub promises notice before that changes ([GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)).

## Open

- Whether to move to GitHub Pro so that GitHub enforces the merge rule on `main`.

# ADR-0002: The embedding model is chosen per workspace

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The first PRD draft named BGE-M3. The vendor noted that another embedding model can be used, and chose a per-workspace choice, for example by language.

OneClickDZ visitors write Arabic, Darija, French and English, often mixed in one message. The September design defers the model choice to a bake-off on real Darija traffic (`support-agent-platform/BACKLOG.md`, C2).

## Decision

Each workspace is configured with its own embedding model.

## Consequences

- Every chunk records the model and version that embedded it.
- Changing a workspace's model re-embeds that workspace. The old index serves until the new one is complete (PRD KB-12).
- Vector size can differ between workspaces, so storage cannot assume one fixed dimension.
- Retrieval relevance thresholds are calibrated per model, and therefore per workspace.

## Open

- What a workspace is when each business runs its own copy: the whole install, or one of several.
- How a model is chosen for a workspace, and by whom.

## Update, 2026-10-05 (grilling round 4)

One install has exactly one workspace, serving one website, so the embedding model is chosen per install. The business's Owner chooses it in the dashboard ([ADR-0011](0011-cpu-first-models.md)).

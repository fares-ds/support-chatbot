# ADR-0006: Each business runs its own install

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The architecture diagram showed one shared platform with a Neon branch per tenant, and the September design was multi-tenant from day one. In grilling round 1 the vendor chose one copy per business, and kept that choice in round 2 by setting the earlier designs aside ([ADR-0005](0005-standalone-industry-agnostic-product.md)).

## Decision

Each business runs its own copy of Support Chatbot, used by that business alone. There is no shared, multi-tenant platform in V1.

## Consequences

- Cross-tenant isolation leaves V1: no branch per tenant, no control branch, no cross-tenant test suite. Neon branching has no tenancy role left.
- Installing, upgrading and backing up a copy become product work, because every business has to do them.
- OneClickDZ's test install runs on a Contabo VPS.

## Open

- Who operates an install: the business, or the vendor on its behalf.
- Whether one install can hold several workspaces ([ADR-0002](0002-embedding-model-per-workspace.md)).

## Update, 2026-10-05 (grilling round 3)

The business operates its install, with the vendor's support; the vendor installs it ([ADR-0009](0009-vendor-installs-business-operates.md)).

## Update, 2026-10-05 (grilling round 4)

One install serves exactly one website, with one workspace. The vendor operates every install over server access ([ADR-0012](0012-vendor-operates-every-install.md)).

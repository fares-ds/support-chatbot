# ADR-0001: Model providers sit behind one interface

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The architecture diagram excluded every proprietary service ("No OpenAI"), so the first PRD draft assumed self-hosted models only. In grilling round 1 the vendor required that external AI model APIs (LLMs, embeddings) be usable too.

The first design partner, OneClickDZ, requires its data to stay in Algeria. The September design (`support-agent-platform/docs/support-agent-design.md`, §12) treats sending customer data to a cloud model as blocked until counsel signs off under Law 18-07. That question is still open (`support-agent-platform/BACKLOG.md`, Track A).

## Decision

Every model call (classification, answering, embedding, reranking) goes through one provider interface. An install can point it at self-hosted models or at external APIs. The choice is configuration, not code.

## Consequences

- "100% open source, no proprietary services" is no longer a product rule. It becomes one possible install configuration.
- Whether an install may use an external provider depends on that install's data-residency requirement. For OneClickDZ this is open.
- Evaluation results hold per provider configuration. Switching provider means re-running the release gates.

## Update, 2026-10-05 (grilling round 2)

The open point for OneClickDZ is settled by [ADR-0008](0008-regulations-out-of-scope-for-v1.md): regulations are out of scope for V1, so the test install may use external providers.

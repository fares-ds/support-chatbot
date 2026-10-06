# ADR-0025: CPU-mode classifier fallbacks and uncalibrated models

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares
- Refines: [ADR-0024](0024-stack-review-corrections.md)

## Context

A final review of the PRD found two gaps left by the stack review.

- The cheaper CPU classifier ([ADR-0024](0024-stack-review-corrections.md), item 4) can be an embedding-similarity check. That check sees only the current message, so it cannot rewrite follow-up questions, read the conversation, or detect the language for canned replies.
- Gate 2's relevance threshold is set per model by the vendor, but the Owner may pick any embedding model or reranker ([ADR-0011](0011-cpu-first-models.md)).

## Decision

1. **CPU classifier.** M0 keeps both options, the embedding check and a small model, and picks one. If it picks the embedding check:
   - the search query is the customer's previous message plus the new one
   - a short "yes" right after the AI offered a person counts as a request for a person
   - canned replies use the widget's interface language
2. **Uncalibrated models.** For an embedding model or reranker the vendor has not calibrated, retrieval keeps the top 5 chunks with no relevance cut-off, and the answer model's abstain token is the only gate. The dashboard marks the model "uncalibrated" until the test set calibrates it.

## Consequences

- In CPU mode with the embedding check, follow-up questions are retrieved less precisely than with a small model. M0 weighs that against speed.
- With an uncalibrated model, unanswerable questions depend on the answer model abstaining, so more of them may get an answer instead of a handoff until calibration.

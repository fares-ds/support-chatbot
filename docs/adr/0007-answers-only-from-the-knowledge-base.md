# ADR-0007: The AI answers only from the knowledge base

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The September design gave the AI read-only tools over live business data, because for OneClickDZ "a knowledge base alone answers almost none" of the recurring issues. The vendor chose documents-only in grilling round 1 and kept it in round 2, treating OneClickDZ as a test use case only ([ADR-0005](0005-standalone-industry-agnostic-product.md)).

## Decision

In V1 the AI answers only from the business's knowledge base. It has no tools, no live-data lookups and no actions. When the knowledge base does not answer, the conversation goes to a person.

## Consequences

- Questions that need account or transaction data always hand off. For OneClickDZ that covers most of its recurring issues, so expect a high handoff rate and low containment in that test.
- Visitors stay anonymous; V1 needs no identity verification.
- The prompt-injection surface stays small, because the model can only produce text.

## Update, 2026-10-05 (grilling round 5)

Customers are now logged in ([ADR-0016](0016-logged-in-customers.md)), so the consequence "visitors stay anonymous" no longer holds. Knowing who the customer is does not change this decision: the AI still answers only from the knowledge base and looks up no account data.

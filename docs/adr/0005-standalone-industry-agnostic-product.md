# ADR-0005: Support Chatbot is a standalone product for any industry

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

Two earlier projects overlap with this one: `oneclickdz/ai-support-api`, a support RAG service, and `support-agent-platform`, whose September design targeted OneClickDZ first. Neither reached production. Their designs disagree with this PRD on tenancy, tools, visitor identity, knowledge format, first release and answer delivery.

## Decision

Support Chatbot is a new, independent product for businesses in any industry. OneClickDZ is a use case to test it, not the customer it is shaped around. The earlier projects are not reused; they serve only as a source for the tech stack.

## Consequences

- Requirements stay generic. A need only OneClickDZ has does not enter V1 because of OneClickDZ.
- The September design's concepts (audiences, trust levels, tools, articles, resolved cases, staff copilot) are not part of V1.
- Code from the earlier projects is not imported.

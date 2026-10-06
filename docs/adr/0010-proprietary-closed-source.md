# ADR-0010: Support Chatbot is proprietary

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The architecture diagram described a "100% open source" stack. Whether the product itself would be open source was never stated.

## Decision

Support Chatbot is closed source. It is not published as open source.

## Consequences

- Every component and model weight shipped inside an install needs a license that allows distribution as part of a proprietary product. License review becomes part of choosing any component or model.
- "100% open source" in the architecture diagram describes the components, not the product.

## Open

- Which licenses are acceptable for shipped components and model weights.
- Whether V1 enforces licensing technically (for example, a license key) or by contract only.

## Update, 2026-10-05 (grilling round 4)

License enforcement and licensing questions are deferred until the product is offered to other companies. Components chosen now under licenses such as AGPL or SSPL may have to be replaced then.

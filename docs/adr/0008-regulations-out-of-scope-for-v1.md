# ADR-0008: Regulations are out of scope for V1

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

OneClickDZ said its data must stay in Algeria. The vendor also wants external model APIs ([ADR-0001](0001-model-providers-behind-one-interface.md)) and runs the test install on a Contabo VPS. In grilling round 2 the vendor set regulatory requirements aside for now.

## Decision

V1 does not design for data residency or other regulatory requirements.

## Consequences

- The OneClickDZ test install may use external model APIs, so its data may leave Algeria.
- The regulatory risk of the test install is accepted, not mitigated.
- The PRD's security and privacy requirements (encryption, access control, deletion) still apply. They are product quality, not compliance.
- Revisit before any business with a residency requirement goes live.

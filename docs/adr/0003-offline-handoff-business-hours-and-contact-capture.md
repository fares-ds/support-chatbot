# ADR-0003: Outside business hours, a handoff collects contact details

- Status: Superseded by [ADR-0015](0015-every-handoff-notifies-the-team.md)
- Date: 2026-10-05
- Deciders: Fares

## Context

V1 has no email or notifications. A visitor handed off while nobody is working would wait indefinitely, and would see a reply only if they came back.

## Decision

Each workspace sets business hours. Outside them, a handoff shows a different message and asks the visitor for contact details, so the team can follow up outside the product.

## Consequences

- The product stores visitor contact details. They are personal data, so consent wording, retention and deletion apply.
- Agents need to see which conversations are waiting for an outside follow-up, and to mark them done.

## Open

- Which contact fields, which are required, and the consent text.
- Time zone, weekly schedule, public holidays and Ramadan hours.
- Whether the AI keeps answering outside business hours.
- What happens during business hours when no agent is online.

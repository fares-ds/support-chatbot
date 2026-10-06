# ADR-0022: Evaluation data comes from the live beta

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares

## Context

The PRD's release gates need test questions with known correct answers, and its launch criteria required passing every gate on the design partner's dataset. In grilling round 7 the vendor chose to collect that data during the beta itself, from agent flags and the weekly review, rather than from past chats, OneClickDZ's team or questions written in advance.

## Decision

There is no test set before the OneClickDZ beta starts. The test set is built from the beta's own conversations.

## Consequences

- The release gates cannot run before customers first see AI answers. The beta is the first real test of answer quality.
- The PRD's launch criterion "passes every release gate on their dataset" applies only once enough beta conversations are labelled.
- After that, every model, prompt or retrieval change is gated as the PRD describes.

## Open

- How the beta is protected until the test set exists.

## Update, 2026-10-06 (grilling round 7)

The beta launches with the AI answering customers from day one. Agent flags and the weekly review are the only quality check until the test set exists.

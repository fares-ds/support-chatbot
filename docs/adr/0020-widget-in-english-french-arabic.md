# ADR-0020: The widget's interface is in English, French and Arabic

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The first PRD draft shipped the widget in English only, while the AI replied in the customer's language. OneClickDZ's customers write Arabic, Darija, French and English.

## Decision

The widget's interface (buttons, labels, notices) is available in English, French and Arabic. Arabic uses a right-to-left layout.

## Consequences

- Every widget string, system notice and template (greeting, decline, handoff, closed) exists in all three languages.
- The widget layout must work right-to-left, including mixed-direction messages.
- The PRD non-goal "widget UI in English" no longer holds.

## Open

- How the widget picks its language: the identity token's `language`, the browser's language, or an install default.

## Update, 2026-10-06 (grilling round 7)

The widget uses the `language` from the customer's identity token; without one, the browser's language; without a match, the install's default language.

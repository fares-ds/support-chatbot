# ADR-0015: Every handoff notifies the whole team

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares
- Supersedes: [ADR-0003](0003-offline-handoff-business-hours-and-contact-capture.md)

## Context

ADR-0003 changed the handoff outside business hours and collected the visitor's contact details. In grilling round 5 the vendor made every handoff behave the same, inside or outside business hours. The vendor also noted that customers are logged in, so their contact details are already known ([ADR-0016](0016-logged-in-customers.md)).

## Decision

- When a conversation needs a person, every team member is notified, and one of them replies as soon as possible.
- The customer is told that the team will get back to them, by email or another communication channel.
- Business hours do not change this behavior.

## Consequences

- No contact-capture form in V1. The customer's contact details come from their login.
- Notifications must reach team members who are not looking at the dashboard, so delivering them becomes V1 work.

## Open

- Notification channels (dashboard, email, messaging apps), and whether to notify again when nobody replies.
- Whether the human reply happens in the chat, outside the product by email or phone, or both; and whether the product itself sends email.
- Whether business hours remain in V1 at all.

## Update, 2026-10-05 (grilling round 6)

- Team notifications stay inside the dashboard: sound, badge and browser notification. There is no email or messaging-app notification, so a handoff reaches only team members who have the dashboard open.
- The person answers live in the chat. If the customer has left, the agent contacts them by email or phone outside the product. The product sends no email in V1.
- Business hours leave V1 entirely.

## Update, 2026-10-05 (grilling round 7)

Browser notifications work only while a dashboard tab is open; there is no Web Push. When no dashboard tab is open anywhere, nobody is alerted until someone opens the dashboard.

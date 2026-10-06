# ADR-0018: How the widget identifies customers and treats visitors

- Status: Accepted (approved in grilling round 6)
- Date: 2026-10-05
- Deciders: Fares

## Context

Each install chooses whether only logged-in customers can chat, or anonymous visitors too, with more restrictions on visitors ([ADR-0016](0016-logged-in-customers.md), grilling round 6). The vendor asked to follow the standard approach for identity, and to copy Intercom for the details. What Intercom does:

- **Signed identity.** The business's server signs the logged-in user's identity with a secret. Intercom recommends a signed token (JWT) over its older HMAC hash, because without one, attackers can impersonate users and see their conversation history ([Intercom developer docs](https://developers.intercom.com/installing-intercom/web/identity-verification)).
- **Identity fields.** `user_id` and `email` identify the logged-in user; `name`, `phone`, `created_at`, `language_override` and custom attributes describe them ([Intercom attributes](https://developers.intercom.com/installing-intercom/web/attributes-objects/)).
- **Separate launcher settings** for logged-out visitors and logged-in users, each with its own display conditions ([Intercom help](https://www.intercom.com/help/en/articles/1155368-control-who-can-see-the-messenger-launcher-on-your-site)).
- **Visitors become users.** A visitor who starts a conversation becomes a lead. When they log in, their information and conversations stay with their user profile ([Intercom help](https://www.intercom.com/help/en/articles/310-how-do-visitors-leads-and-users-work-in-intercom)).
- **Email from logged-out people.** An optional setting requires an email before the first message: always (about 30% fewer conversations on average) or only outside office hours (about 5% fewer) ([Intercom help](https://www.intercom.com/help/en/articles/2301967-require-leads-to-give-their-email-to-start-a-conversation)).

## Proposal

1. **Signed identity token.** The business's server issues a short-lived JWT for the logged-in customer, signed with the install's identity secret. The widget sends it when a session starts; the install rejects identities that are unsigned, wrongly signed or expired.
2. **Token fields.** `user_id` is required and stable. `email`, `name`, `phone` and `language` are optional. Agents see them in the conversation.
3. **Two bubble settings per install:** show to logged-in customers (on by default) and show to logged-out visitors (off by default).
4. **Visitor to customer.** When a visitor who has chatted logs in on the same browser, their conversations move to the customer's history.
5. **Visitor restrictions:** open, see below.

## Consequences

- Integration needs server-side work at the business, to issue the token. For logged-in customers, the snippet alone is no longer enough.
- The identity secret is per install and can be rotated. Rotation invalidates tokens signed with the old secret.
- Logging out must clear the customer's conversations from the widget on that browser.

## Open

- Which restrictions apply to visitors: contact details before the first message, contact details only before a handoff, AI only with no handoff, stricter rate limits, or a combination.

## Update, 2026-10-05 (grilling round 7)

Visitor restrictions are tighter limits only: lower message rate limits and a smaller daily AI budget than customers. Visitors give no contact details and can still be handed to a person. Consequences:

- An agent can answer a visitor only while the visitor is in the chat, or after they return on the same browser.
- The handoff message to a visitor must not promise a follow-up by email or phone.

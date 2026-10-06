# ADR-0017: Returning customers and closing conversations

- Status: Accepted (approved in grilling round 6)
- Date: 2026-10-05
- Deciders: Fares

## Context

The vendor asked to copy what similar products do when a customer comes back to a finished conversation. Two established products:

- **Intercom.** By default a customer can reply to a closed conversation at any time, and the reply reopens it. An optional setting blocks replies after a set number of days without activity; the customer can still read the old conversation but starts a new one ([Intercom help](https://www.intercom.com/help/en/articles/3449698-Prevent-replies-after-you-close-a-conversation)).
- **Zendesk.** A solved ticket closes automatically after 4 days by default, adjustable from 1 hour to 28 days. A reply to a solved ticket reopens it; a reply to a closed ticket creates a new follow-up ticket ([Zendesk help](https://support.zendesk.com/hc/en-us/articles/4408887712154)).

## Proposal

1. **Two end states.** An agent marks a conversation Resolved. After 4 days without activity it becomes Closed. The Owner can change the delay.
2. **A reply to a Resolved conversation reopens it.** If a person handled it, it goes back to that person, who is notified. Otherwise it returns to AI answering.
3. **A reply to a Closed conversation starts a new one,** linked to the old one so agents see the history. The customer can still read closed conversations in the widget.
4. **Idle AI conversations resolve themselves** after 24 hours without a customer message.
5. **Conversations waiting for or handled by a person never close on their own.** Only an agent resolves them.

## Consequences

- The conversation states become five: AI answering, Waiting, Human, Resolved, Closed.
- The widget shows a customer's list of conversations, not one endless thread. That works because customers are logged in ([ADR-0016](0016-logged-in-customers.md)).

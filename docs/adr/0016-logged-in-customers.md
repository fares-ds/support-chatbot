# ADR-0016: Customers chat while logged in to the business's app

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The PRD assumed anonymous website visitors, identified only by a token in their browser. In grilling round 5 the vendor stated that only users logged in to the business's application can use the chatbot, so the business already knows their name, email and phone number.

## Decision

The widget chats with customers who are logged in to the business's application. Their identity, including contact details, comes from that login.

## Consequences

- The business must tell the install who the customer is in a way that cannot be forged. Otherwise anyone could claim another customer's identity and read their conversation history.
- Integration is no longer only a snippet: the business's backend has to take part in identifying the customer.
- The install stores customer personal data: name, email, phone.
- Conversations follow the customer across devices and browsers.
- For logged-in customers, the PRD's anonymous-visitor requirement (W-4) and the non-goal "no identified (logged-in) visitors" no longer hold.

## Open

- Whether every install requires login, or each install chooses whether anonymous visitors may chat too.
- How identity is passed and verified, which fields are required, and what logged-out visitors see.

## Update, 2026-10-05 (grilling round 6)

- Each install chooses: logged-in customers only, or anonymous visitors too, with more restrictions on visitors.
- Identity follows the standard approach, in which the business's server signs it. The details are proposed in [ADR-0018](0018-customer-identity-and-visitors.md).

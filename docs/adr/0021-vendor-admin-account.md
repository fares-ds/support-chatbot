# ADR-0021: The vendor has an admin account on every install

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares

## Context

The vendor operates every install's server ([ADR-0012](0012-vendor-operates-every-install.md)). The dashboard had two roles, Owner and Agent.

## Decision

Every install has a vendor admin account. It can do everything an Owner can, including reading all conversations, so the vendor can support the business from inside the product.

## Consequences

- The dashboard has three roles: Owner, Agent and Vendor admin.
- Businesses need to know that the vendor can read their conversations and customer data.

## Open

- Whether the Owner can see, disable or remove the vendor admin account.
- Whether vendor access to conversations is logged and visible to the Owner.

## Update, 2026-10-06 (grilling round 7)

The vendor admin account appears in the install's team list. The Owner can see it but cannot remove or disable it. Logging of vendor access stays open.

# ADR-0023: How long data is kept

- Status: Accepted (approved in grilling round 7)
- Date: 2026-10-06
- Deciders: Fares

## Context

The vendor asked to copy Intercom. What Intercom does:

- Visitors who have not been seen for 9 months are deleted automatically, with their whole record and event history. User data is unaffected ([Intercom help](https://www.intercom.com/help/en/articles/1722980-how-intercom-tracks-and-stores-data)). In Intercom's terms a visitor has no conversation history; someone who starts a conversation becomes a lead ([Intercom help](https://www.intercom.com/help/en/articles/310-how-do-visitors-leads-and-users-work-in-intercom)).
- Deleting a conversation is permanent and cannot be undone ([Intercom help](https://www.intercom.com/help/en/articles/13885146-deleting-a-conversation)).
- All data linked to one person can be permanently deleted, for erasure requests ([Intercom help](https://www.intercom.com/help/en/articles/1385437-how-intercom-complies-with-gdpr)).

## Proposal

1. Conversations, customers, and visitors who have chatted are kept until someone deletes them. Nothing expires on its own.
2. Visitor records with no conversation are deleted automatically after 9 months without a visit.
3. The Owner, or the vendor admin, can permanently delete a conversation, or a customer with all of that customer's conversations. Deletion cannot be undone.

## Consequences

- Deleted data stays in backups until those backups expire, so backup retention ([ADR-0012](0012-vendor-operates-every-install.md)) also bounds how long deleted data survives.
- The PRD's owner-only "delete a conversation" (D-10) becomes part of V1, together with "delete a customer".

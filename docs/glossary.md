# Glossary

The words the PRD, the code and the team use for this product, one meaning per word. Entries marked **Open** are not settled yet.

Updated 2026-10-08, with the machine account (ADR-0031), the service account (ADR-0032), backups and snapshots (ADR-0033), the upgrade test's smoke test and seeds, and the upgrade path (ADR-0034).

## People and roles

| Term | Meaning | Not to be confused with |
| --- | --- | --- |
| Business | The organization that deploys Support Chatbot to support its own customers. OneClickDZ is the first. | |
| Vendor | Fares, who builds Support Chatbot, installs it for businesses and operates every install. A team of one in V1. | Owner |
| Design partner | A business using V1 before general release, onboarded directly by the vendor ([ADR-0004](adr/0004-invite-only-design-partners.md)). OneClickDZ is the first, as a test use case, not the customer the product is shaped around ([ADR-0005](adr/0005-standalone-industry-agnostic-product.md)). | |
| Customer | A person logged in to the business's application, chatting through the widget. Identity and contact details come from that login ([ADR-0016](adr/0016-logged-in-customers.md)). | Business (the vendor's customer) |
| Visitor | An anonymous person chatting through the widget. Exists only on installs that allow visitors, with more restrictions than customers ([ADR-0016](adr/0016-logged-in-customers.md)). | Customer |
| Owner | A business's administrator in the dashboard: settings, knowledge, team, AI switch. | Vendor, Operator |
| Agent | A human support team member. In code and screens the word means a human only (round 5). | AI assistant |
| AI assistant | The automated responder in the widget, and its name in code and screens (round 5). Customers see the display name the Owner sets; its messages stay labelled as AI whatever the name. | Agent |
| Operator | Whoever keeps an install running. In V1, the vendor, over server access ([ADR-0012](adr/0012-vendor-operates-every-install.md)). | Owner |
| Vendor admin | The vendor's account inside each install's dashboard. Can do everything an Owner can, including reading conversations. Visible in the team list; the Owner cannot remove or disable it ([ADR-0021](adr/0021-vendor-admin-account.md)). | Owner |

## Deployment

| Term | Meaning |
| --- | --- |
| Install | One running copy of Support Chatbot, hosted by one business for its own use ([ADR-0006](adr/0006-one-install-per-business.md)). |
| Workspace | The same thing as an install in V1: one website, one widget, one knowledge base, one team. The PRD's "workspace settings" are the install's settings. |
| Model provider | Where model calls go: a local model or an external provider ([ADR-0001](adr/0001-model-providers-behind-one-interface.md)). |
| Local model | A small model running on the install's own CPU and RAM; no GPU needed ([ADR-0011](adr/0011-cpu-first-models.md)). |
| External provider | A model service outside the install, reached over an API, used for larger models ([ADR-0011](adr/0011-cpu-first-models.md)). |
| CPU mode | How an install runs when its models use the server's CPU: a cheaper classifier, the answer model as the only large model loaded, and latency targets from the M0 benchmark ([ADR-0024](adr/0024-stack-review-corrections.md)). Fallbacks for the embedding check: [ADR-0025](adr/0025-cpu-classifier-fallbacks-and-uncalibrated-models.md). |
| Uncalibrated model | An embedding model or reranker whose relevance threshold the vendor has not calibrated. Retrieval applies no cut-off, and the dashboard marks the model ([ADR-0025](adr/0025-cpu-classifier-fallbacks-and-uncalibrated-models.md)). |
| Release | A `vX.Y.Z` tag on `main`. It versions every image and the install bundle together ([ADR-0027](adr/0027-repository-layout-and-git-workflow.md)). |
| Install bundle | What the vendor installs and upgrades from: the Compose file, the environment template and the server CLI, published with each release (OPS-1). |
| Service account | `supportchatbot`, the system user an install runs as. It owns `/opt/support-chatbot` and alone can read the install's secrets ([ADR-0032](adr/0032-dedicated-service-account.md)). |
| Machine account | The vendor's second GitHub account. It holds each install's read-only pull token, and can read only our two packages ([ADR-0031](adr/0031-pull-tokens-from-a-machine-account.md)). |
| Backup | A restic snapshot of an install's database dump and stored files, sent encrypted to the install's backup repository off the server. `sc backup` takes one daily from the host's cron. It leaves out `.env`, whose copy the vendor keeps in a password manager ([ADR-0033](adr/0033-backups-leave-out-the-encryption-key.md)). |
| Snapshot | One backup in the repository, named by its ID. `sc restore` brings an install's data back as of one, the latest by default. |
| Smoke test | The check that a release runs on a database: its migration job, API and worker start, Postgres and Valkey answer, and the worker writes a fresh heartbeat that the API reads back. The upgrade test runs it for both releases; it grows with M1's endpoints. |
| Pre-upgrade backup | The snapshot `sc upgrade` takes before changing anything, tagged `pre-upgrade`. A rollback restores it only if the previous release cannot run on the migrated database. |
| Upgrade path | The installed versions a release upgrades from: the release its upgrade test started from, recorded in the bundle's `release.txt`, or a later one ([ADR-0034](adr/0034-upgrade-from-the-tested-release.md)). |
| Upgrade seed | The rows the upgrade test puts in the previous release's database, one SQL file per migration revision that adds a table, in `backend/tests/upgrade_seeds/`. |
| Stored files | Uploaded files and their parsed text, on the install's files volume (`/data/files`). Backed up with the database. |

## Conversations

| Term | Meaning |
| --- | --- |
| Conversation | One thread between a visitor and the business, across AI and human replies. |
| AI answering | The default conversation state, and the only one in which the AI assistant writes. |
| Waiting | A conversation that needs a person. The AI is silent. |
| Human | A conversation an agent has taken. The AI is silent. |
| Closed | Finished for good. A new message starts a new conversation, linked to this one ([ADR-0017](adr/0017-returning-customers-and-closing.md)). |
| Handoff | The AI moving a conversation from AI answering to Waiting. Every team member is notified ([ADR-0015](adr/0015-every-handoff-notifies-the-team.md)). |
| Takeover | An agent moving a conversation to Human. |
| Turn | One run of the AI pipeline, for one or more visitor messages. |
| Abstain | The answer model declaring the sources insufficient, which triggers a handoff. |
| Business hours | Not in V1 (grilling round 6). |
| Follow-up | The team getting back to a customer after a handoff: live in the chat, or, if the customer has left, by email or phone outside the product ([ADR-0015](adr/0015-every-handoff-notifies-the-team.md)). |
| Identity token | A short-lived JWT the business's server signs to tell the install who the logged-in customer is ([ADR-0018](adr/0018-customer-identity-and-visitors.md)). |
| Resolved | Marked done by an agent; a customer reply reopens it with the same person. Becomes Closed after 4 idle days, a delay the Owner can change ([ADR-0017](adr/0017-returning-customers-and-closing.md)). |

## Knowledge

| Term | Meaning |
| --- | --- |
| Knowledge base | The material the AI may answer from. |
| Document | One knowledge source: an uploaded file (PDF, DOCX, Markdown, text) or an imported web page ([ADR-0019](adr/0019-web-pages-as-knowledge.md)). |
| Chunk | A retrievable section of a document, with its embedding. |
| Business description | The owner-written scope the classifier uses to judge what is on-topic. |

## Terms from the September design that V1 does not use

From `support-agent-platform/docs/support-agent-design.md`. None is part of V1 ([ADR-0005](adr/0005-standalone-industry-agnostic-product.md)); they are listed so nobody brings them in from the old code by accident.

| Term | Meaning there |
| --- | --- |
| Tenant | One business on a shared, multi-tenant platform. |
| Audience | Consumer, API partner, POS reseller or internal staff, each with its own prompt, knowledge namespace and tools. |
| Trust level | Anonymous, verified or staff. Decides what data the AI may read. |
| Article | Knowledge written in an editor, French first, translated to MSA and Darija at publish time. |
| Resolved case | A past conversation, PII stripped, used to find the right article. |
| Tool, connector | A reviewed, read-only query against live business data, and the data source it runs on. |
| Console | The agents' workspace, including a copilot panel. |
| Copilot | AI suggestions shown to agents only, never sent to customers directly. |

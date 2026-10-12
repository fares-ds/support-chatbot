# Architecture decision records

Every decision behind Support Chatbot V1, in order. The PRD's [decision history](../prd.md#appendix-a-decision-history) summarizes them; each file holds the full context, decision and consequences.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-model-providers-behind-one-interface.md) | Model providers sit behind one interface | Accepted |
| [0002](0002-embedding-model-per-workspace.md) | The embedding model is chosen per workspace (one workspace per install) | Accepted; amended by 0030 |
| [0003](0003-offline-handoff-business-hours-and-contact-capture.md) | Outside business hours, a handoff collects contact details | Superseded by 0015 |
| [0004](0004-invite-only-design-partners.md) | V1 is invite-only for design partners | Accepted |
| [0005](0005-standalone-industry-agnostic-product.md) | Support Chatbot is a standalone product for any industry | Accepted |
| [0006](0006-one-install-per-business.md) | Each business runs its own install | Accepted |
| [0007](0007-answers-only-from-the-knowledge-base.md) | The AI answers only from the knowledge base | Accepted |
| [0008](0008-regulations-out-of-scope-for-v1.md) | Regulations are out of scope for V1 | Accepted |
| [0009](0009-vendor-installs-business-operates.md) | The vendor installs; the business runs the install | Accepted; the maintenance part is superseded by 0012 |
| [0010](0010-proprietary-closed-source.md) | Support Chatbot is proprietary | Accepted |
| [0011](0011-cpu-first-models.md) | Installs run on CPU; larger models go through external providers | Accepted; amended by 0030 |
| [0012](0012-vendor-operates-every-install.md) | The vendor operates every install over server access | Accepted |
| [0013](0013-upgrades-and-migrations.md) | How installs are upgraded | Accepted |
| [0014](0014-v1-tech-stack.md) | Tech stack for V1 | Accepted; amended by 0024 |
| [0015](0015-every-handoff-notifies-the-team.md) | Every handoff notifies the whole team | Accepted |
| [0016](0016-logged-in-customers.md) | Customers chat while logged in to the business's app | Accepted |
| [0017](0017-returning-customers-and-closing.md) | Returning customers and closing conversations | Accepted |
| [0018](0018-customer-identity-and-visitors.md) | How the widget identifies customers and treats visitors | Accepted |
| [0019](0019-web-pages-as-knowledge.md) | Web pages are a knowledge source | Accepted |
| [0020](0020-widget-in-english-french-arabic.md) | The widget's interface is in English, French and Arabic | Accepted |
| [0021](0021-vendor-admin-account.md) | The vendor has an admin account on every install | Accepted |
| [0022](0022-eval-data-from-the-live-beta.md) | Evaluation data comes from the live beta | Accepted |
| [0023](0023-data-retention.md) | How long data is kept | Accepted |
| [0024](0024-stack-review-corrections.md) | Stack corrections after the stack review | Accepted; refined by 0025, amended by 0028 |
| [0025](0025-cpu-classifier-fallbacks-and-uncalibrated-models.md) | CPU-mode classifier fallbacks and uncalibrated models | Accepted |
| [0026](0026-typed-api-client-from-openapi.md) | The TypeScript API client is generated from FastAPI's OpenAPI spec | Accepted |
| [0027](0027-repository-layout-and-git-workflow.md) | One repository with a root per toolchain, and a trunk-based workflow | Accepted |
| [0028](0028-two-tei-containers.md) | Embeddings and reranking run in two TEI containers | Accepted |
| [0029](0029-server-cli-in-standard-library-python.md) | The server CLI is a standard-library Python script | Accepted |
| [0030](0030-vendor-sets-local-embedding-and-rerank-models.md) | The vendor sets each install's local embedding model and reranker | Accepted |
| [0031](0031-pull-tokens-from-a-machine-account.md) | Install pull tokens come from a machine account | Accepted |
| [0032](0032-dedicated-service-account.md) | An install runs as a dedicated service account | Accepted |
| [0033](0033-backups-leave-out-the-encryption-key.md) | Backups leave out the encryption key | Accepted |
| [0034](0034-upgrade-from-the-tested-release.md) | A release upgrades from the release CI tested it from | Accepted |
| [0035](0035-darija-replies-in-arabic-script.md) | A Darija message gets its reply in Darija or Modern Standard Arabic | Accepted |

## Adding a decision

1. Copy the format of an existing ADR: Status, Date, Deciders, Context, Decision, Consequences, and Open when something is unresolved.
2. Take the next number (ADR-0036 next). Never renumber or delete an ADR. To change a decision, write a new ADR that supersedes or amends it, and update the old one's status line.
3. Add a row here and in the PRD's decision history, update the PRD sections the decision changes, and update the [glossary](../glossary.md) if it introduces or changes a term.

# ADR-0011: Installs run on CPU; larger models go through external providers

- Status: Accepted; amended by [ADR-0030](0030-vendor-sets-local-embedding-and-rerank-models.md)
- Date: 2026-10-05
- Deciders: Fares

## Context

The first PRD draft assumed GPU serving (vLLM in production). Installs run on business-owned VPSs ([ADR-0009](0009-vendor-installs-business-operates.md)), and OneClickDZ's VPS has no GPU.

## Decision

- An install never requires a GPU.
- The product offers several model options: small models that run locally on the install's CPU and RAM, and larger models through external providers ([ADR-0001](0001-model-providers-behind-one-interface.md)).
- Small local models are preferred where they perform well enough for support conversations.

## Consequences

- Local model choices are limited to what runs acceptably on CPU. Their speed and quality must be measured on the target VPS.
- The PRD's latency targets and prompt budgets assumed GPU serving, and must be revisited for CPU installs.
- Evaluation runs per model option, because each option behaves differently.

## Open

- Which steps run locally by default: classification, embeddings, reranking, answering.
- Which latency targets apply to CPU installs.
- Who chooses an install's models: the vendor at install time, or the business's Owner in the dashboard.

## Update, 2026-10-05 (grilling round 4)

- CPU installs get relaxed latency targets. The values are open.
- OneClickDZ's VPS can run 4–7B models. Its exact specs are unknown.
- If no CPU-sized model passes the quality gates for a language, that install answers through an external provider.
- The business's Owner chooses the models in the dashboard: an external provider, or a local model through Ollama or vLLM. This reverses the PRD non-goal "no per-workspace model choice".

## Update, 2026-10-05 (grilling round 5)

- The Owner may choose any model, at the Owner's own risk. The vendor does not certify models, and the release gates cover only the vendor's own test configurations.
- OneClickDZ's VPS specs are still unknown, so CPU latency targets wait for a benchmark on that server.

## Update, 2026-10-06 (stack review)

Local models run on Ollama. Instead of shipping vLLM, the model settings accept any OpenAI-compatible endpoint, which covers vLLM on a GPU host. When classification would run on CPU, a cheaper classifier is used ([ADR-0024](0024-stack-review-corrections.md)).

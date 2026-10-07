# ADR-0030: The vendor sets each install's local embedding model and reranker

- Status: Accepted
- Date: 2026-10-07
- Deciders: Fares
- Amends: [ADR-0002](0002-embedding-model-per-workspace.md), [ADR-0011](0011-cpu-first-models.md)

## Context

The PRD lets the Owner choose the embedding model and the reranker in the dashboard, either a local model on TEI or an external API (AI-2, D-19). Changing the embedding model re-embeds the knowledge base, with the old model serving until the new index is complete (KB-14).

A TEI container loads one model, named when the container starts ([ADR-0028](0028-two-tei-containers.md)). So choosing a different local model means restarting TEI with it, and the API cannot restart containers: that would need the Docker socket, which gives root on the host. Re-embedding from one local model to another would also need both models served at once.

Ollama, by contrast, pulls and loads models on request, so the Owner can still change the local classifying and answering models from the dashboard.

## Decision

- The vendor sets each install's local embedding model and local reranker in the install's environment file (`SC_EMBEDDING_MODEL`, `SC_RERANK_MODEL`), as the vendor already sets the starting models (AI-5). Changing them is a vendor operation over server access.
- In the dashboard, the Owner chooses for embeddings, and separately for reranking, between the install's local model and an external API.
- Re-embedding (KB-14) runs when the Owner switches embeddings between the local model and an external API, or between external models. Replacing the local embedding model with another local one is a vendor operation.
- The local classifying and answering models stay the Owner's choice (AI-2).

## Consequences

- AI-2, D-19 and KB-14 change to match. The dashboard names the local embedding model and reranker; it cannot change them.
- The Owner still controls where knowledge excerpts and questions go: to the install's own models, or to an external API.

## Open

- How the vendor replaces one local embedding model with another: for example, a second TEI container that serves the new model while the knowledge base is re-embedded. Decided when it is first needed.

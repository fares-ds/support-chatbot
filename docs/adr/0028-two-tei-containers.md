# ADR-0028: Embeddings and reranking run in two TEI containers

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares
- Amends: [ADR-0024](0024-stack-review-corrections.md)

## Context

[ADR-0024](0024-stack-review-corrections.md) (item 12) has one Text Embeddings Inference container serve both embeddings and reranking. A TEI instance loads exactly one model, named by `--model-id`: an embedding model answers `/embed`, and a reranker answers `/rerank` ([TEI](https://github.com/huggingface/text-embeddings-inference)). One container cannot serve both.

TEI also publishes its CPU image per architecture: `cpu-1.9` for x86-64 and `cpu-arm64-1.9` for ARM64. The vendor develops on an ARM64 Mac.

## Decision

- Two TEI containers run from the same image. `tei-embed` serves the install's local embedding model, which the CPU-mode embedding check also uses (AI-8). `tei-rerank` serves the local reranker.
- An install runs eight containers: Caddy, API, worker (with Beat), tei-embed, tei-rerank, Ollama, Postgres and Valkey.
- The TEI image tag follows the server's CPU architecture: `cpu-<version>` on x86-64, `cpu-arm64-<version>` on ARM64.
- As before, each TEI container is needed only while its model is local.

## Consequences

- Two model processes instead of one. The M0 benchmark measures their memory together with the rest of the stack, before the minimum specs are set (OPS-2).
- The "seven containers" in the PRD, the tech stack and ADR-0024 become eight.
- ARM64 servers can run TEI as well. The minimum specs name the supported architectures once M0 has measured them.

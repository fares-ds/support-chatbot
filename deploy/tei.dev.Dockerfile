# Development only. TEI publishes its x86-64 and ARM64 CPU images under different tags, so this
# picks the one for the machine that builds it: an Apple-silicon Mac or an x86-64 CI runner.
# Servers pull the tag in compose.yaml directly (ADR-0028); keep the two versions in step.
ARG TEI_VERSION=1.9.4
FROM ghcr.io/huggingface/text-embeddings-inference:cpu-${TEI_VERSION} AS amd64
FROM ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-${TEI_VERSION} AS arm64
FROM ${TARGETARCH}

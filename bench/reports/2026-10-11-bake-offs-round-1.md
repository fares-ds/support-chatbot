# M0 bake-offs, round 1: cloud models and the Mac's TEI

Run on 2026-10-11 on the vendor's Mac, for #14 (the classifier) and #15 (models and retrieval). The configurations are in [`configs/bake-offs/`](../configs/bake-offs/), and the commands under [Reproducing](#reproducing).

## What ran, and what it can't say

- **Language models ran in Ollama's cloud only.** This Mac's RAM serves other work, so no local model ran (Fares, 2026-10-11). Cloud latency says nothing about an install, so this round compares quality only. None of the cloud models is a CPU candidate: the 1–7B models that would run on an install, and every CPU latency, wait for the VPS run (#17).
- **TEI ran locally,** in Docker Desktop's VM (10 CPUs, 7.75 GiB), one pairing of embedding model and reranker at a time.
- **The data** is #23's three datasets, with #41's expected facts and sources: facts state only what each question asks. Recall and correctness below are scored against #41's labels. Gate 1's labels are the same in both.
- **Arabic and Darija samples.** Fares accepted every one on 2026-10-16 (#13), so the labels below stand. The large classifier agrees with 399 of Acme Pay's 400 labels, which suggests few category errors.

## Gate 1: the classifier (#14)

All 662 samples of the three datasets, classify-only, pooled:

| Classifier | Off-topic declined (≥ 95%) | On-topic wrongly declined (≤ 2%) | Person detected (≥ 98%) |
| --- | ---: | ---: | ---: |
| Embedding check, multilingual-e5-small (dev) | 33.6% (42/125) | 3.1% (8/262) | 88.7% (133/150) |
| Embedding check, multilingual-e5-large | 34.4% (43/125) | 1.1% (3/262) | 92.0% (138/150) |
| Embedding check, bge-m3 | 52.0% (65/125) | 2.3% (6/262) | 96.0% (144/150) |
| Embedding check, Qwen3-Embedding-0.6B\* | 58.4% (73/125) | 6.1% (16/262) | 88.0% (132/150) |
| Embedding check, bge-m3, no on-topic margin | 60.0% (75/125) | 3.4% (9/262) | 96.0% (144/150) |
| gpt-oss:20b (cloud), Gate 1's 120 output tokens | 92.8% (116/125) | 7.3% (19/262) | 82.7% (124/150) |
| Gemma 4 31B (cloud) | **100.0% (125/125)** | **0.0% (0/262)** | **99.3% (149/150)** |

With Gate 1's output budget doubled to 240 tokens, gpt-oss:20b on Acme Pay alone (400 samples, against 120 tokens' 89.3%, 11.9% and 78.9% there) declined 96.0% (72/75) of off-topic messages, wrongly declined 2.5% (4/160), and detected 85.6% (77/90) of requests for a person, with no failed turn.

\* Measured with Qwen3's search instruction on both the messages and the example phrases, which is the wrong task for comparing them. The harness now gives the embedding check its own instruction, but this row wasn't measured again, as it needs the stack and the model reloaded. Its order against the others may change, but not the conclusion below.

**The embedding check can't meet the off-topic gate.**
- On every embedding model it declines between a third and three fifths of off-topic messages, against 95%.
- The harness's 0.05 on-topic margin (`ON_TOPIC_MARGIN` in `bench/classify.py`) explains little: without it, bge-m3 goes from 52% to 60%, and wrongly declines more.
- Each category has about a dozen example phrases, and the nearest one decides. Poems, recipes, sports and homework sit closer to some on-topic phrase than to an off-topic one.
- It does detect requests for a person well on bge-m3, at 96%. But a classifier that answers off-topic messages fails Gate 1.

**A language model can meet all three gates,** as Gemma 4 31B does. Its one miss is `darija-arabic-person-15`, whose "كونساي" reads as *conseil*, advice. That sample is on Fares's review page.

**gpt-oss:20b shows what a reasoning model costs Gate 1.** At Gate 1's 120 output tokens, its reasoning cut 21 of Acme Pay's 400 replies short. All 29 of its failed turns were Arabic or Darija, where text costs more tokens. At 240 tokens nothing failed, but it still missed one Darija request for a person in six. It also called Free Fire and PlayStation questions off-topic, despite a business description that covers game credits.

**Recommendation for #14:** the CPU-mode classifier should be a small language model, not the embedding check, if one of 1–4B meets the three gates and the latency target on the VPS. If none does, Gate 1 needs the external provider (AI-5), or the embedding check needs a redesign: far more examples per category, or a second stage for off-topic messages. That reverses part of AI-8 and ADR-0025, so the decision is Fares's once #17 has the CPU numbers.

**Settled on 2026-10-16.** This accuracy comparison closes #14. The embedding check fails the off-topic gate, declining 34–60% of off-topic messages against 95%, and it gives up follow-up rewriting and language detection ([ADR-0025](../../docs/adr/0025-cpu-classifier-fallbacks-and-uncalibrated-models.md)). A language model can meet all three gates, as Gemma 4 31B does. The CPU classifier is a small model only if one of qwen3.5:2b, granite4:3b, or qwen3.5:0.8b meets the three gates and the latency target on the VPS. That run is #17: classify-only, per language, with off-topic messages declined, on-topic messages wrongly declined, requests for a person detected, and classify p50 and p95. This Mac did not run local models, so this report has no Mac latency. ADR-0025 and AI-8 stay as they are until #17 records the choice. The numbers above are the 11 October figures, unchanged.

## Retrieval (#15)

The answerable questions of all three datasets, retrieve-only. The query is the embedding check's (the previous message plus the new one), so no model varies between pairings.

| Embedding model, with the mMiniLM reranker | acme-pay | ar / darija-latin / darija-arabic | gov-uk | service-public | All |
| --- | ---: | ---: | ---: | ---: | ---: |
| multilingual-e5-small (dev) | 89.8% | 94.3 / 87.5 / 85.4 | 97.8% | 89.7% | 91.5% (195/213) |
| multilingual-e5-large | 88.3% | 94.3 / 90.0 / 78.0 | 95.7% | **100.0%** | 92.0% (196/213) |
| **bge-m3** | **91.4%** | 94.3 / **95.0** / 82.9 | 95.7% | 94.9% | **93.0% (198/213)** |
| Qwen3-Embedding-0.6B\* | 89.1% | 94.3 / 92.5 / 78.0 | 97.8% | 94.9% | 92.0% (196/213) |

\* Its search instruction ended with a space after "Query:" that its model card doesn't have, now removed. That shifts its vectors a little.

Recall@5 is sources found among the reranker's top 5, of the sources needed. All four meet the 90% gate pooled. The spread is three sources of 213, so their order is close to noise, except on Darija.

- **bge-m3** is best on Acme Pay and on Latin-script Darija, and is already production's default ([deploy/compose.yaml](../../deploy/compose.yaml)).
- **Arabic-script Darija is the weak group** for every model, at 78% to 85%. That's where a larger knowledge base would hurt first.
- **The knowledge bases are small,** at 29 to 202 chunks, so recall reads higher than it would over an install's thousands.

**production's default reranker, bge-reranker-v2-m3, is unusable on this CPU as configured.**
- With bge-m3 on 4 of the VM's cores, each rerank of a turn's candidates took 7 to 8 s of inference plus queueing.
- After 4 requests, it stalled for 43 minutes at four cores busy, and the pairing was stopped.
- The mMiniLM reranker the dev stack uses takes about 1.7 s a turn on the same machine.
- So this round has no recall for bge-reranker-v2-m3.

**Recommendation for #15's retrieval:** keep bge-m3 as the embedding model. Take bge-reranker-v2-m3 out as the CPU default, unless the VPS shows it fast enough with fewer candidates or shorter inputs. Measure mMiniLM there as the alternative. The reranker's speed belongs in the first-token latency target, so #17 settles it.

## Answers (#15)

Only Gemma 4 31B (cloud) answered, on Acme Pay's 400 samples. gpt-oss:120b judged it; its verdicts agreed with a hand check on 36 of 38 (#40).

| | en | fr | ar | darija-latin | darija-arabic | All | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Answer correctness | 3/4 | 8/8 | 33/35 | 38/40 | 36/40 | **92.9% (118/127)** | ≥ 85%: met |
| Unsupported claims | 0/3 | 0/8 | 0/34 | 0/38 | 2/38 | **1.7% (2/121)** | ≤ 3%: met |
| Unanswerable answered | 0/1 | 0/2 | 0/10 | 0/10 | 0/10 | **0.0% (0/33)** | ≤ 10%: met |
| Reply in the customer's language | 3/3 | 8/8 | 34/34 | 16/38 | 38/38 | 81.8% (99/121) | ADR-0035 |

- **Against #23's original facts, the same answers scored 80.3%.** Most of the difference is facts that asked for more than the question.
- **Latin-script Darija got French replies 22 times out of 38.** ADR-0035 counts those as the wrong language. Gate 3's rule says "the customer's language", and the model reads Latin-script Darija as French.

**For #15's answer models:** a 31B model meets the answer gates. Whether a 4–7B one does is the question #17 must answer: run qwen3.5:4b and gemma4:e4b there, judged the same way.

## What the VPS run (#17) must settle

1. **Gate 1:** at least two 1–4B models (qwen3.5:2b, granite4:3b, qwen3.5:0.8b were the shortlist) against the three gates, with p50 and p95 classify latency.
2. **The reranker:** bge-reranker-v2-m3 against mMiniLM, for recall@5 and rerank latency.
3. **The answer models:** qwen3.5:4b and gemma4:e4b, judged, with first-token latency at the expected load.
4. **Gate 1's output budget,** if a reasoning model is a candidate.

## Reproducing

From `bench/`, with the dev stack up. Each run takes one dataset: repeat it for `acme-pay`, `gov-uk` and `service-public`.

```sh
# Gate 1 with the cloud models; gate1-gpt-oss-20b-240.toml for the 240-token row
docker compose run --rm bench run configs/bake-offs/gate1-gpt-oss-20b.toml --classify-only --concurrency 4 --dataset data/acme-pay
docker compose run --rm bench run configs/bake-offs/gate1-gemma4-31b.toml --classify-only --concurrency 4 --dataset data/acme-pay
```

The embedding check and retrieval take the embedding model and the reranker TEI serves. Restart TEI with the pairing first, from the repository root:

```sh
SC_EMBEDDING_MODEL=BAAI/bge-m3 SC_RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 docker compose up --detach --wait tei-embed tei-rerank
```

Then, from `bench/`:

```sh
# The embedding check on that embedding model; gate1-embedding-margin-0.toml for the row without the margin
docker compose run --rm bench run configs/dev-embedding.toml --classify-only --concurrency 4 --dataset data/acme-pay
# Retrieval with that pairing
docker compose run --rm bench run configs/dev-embedding.toml --retrieve-only --samples answerable --concurrency 4 --dataset data/acme-pay
```

`docker compose up --detach --wait tei-embed tei-rerank` without the variables brings the dev models back.

```sh
# Answers: every Acme Pay sample once (400 turns), then the judge
docker compose run --rm bench run configs/dev.toml --concurrency 4 --turns 400
docker compose run --rm bench judge results/<run>.json
```

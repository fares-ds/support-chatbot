# Benchmark harness

The M0 benchmark (#12). It times the AI pipeline end to end against a running stack, and scores it against the PRD's release gates (#14, #15), so that M0 can set the CPU numbers the PRD leaves open: latency targets, the classifier mode, default models, prompt budgets and minimum specs ([ADR-0011](../docs/adr/0011-cpu-first-models.md), [ADR-0024](../docs/adr/0024-stack-review-corrections.md)). It needs only the stack, not the product's code, and M3 can run it again against the real pipeline.

## What a turn does

Each turn runs Flow B's steps, as a real turn would:

1. **Classify** (Gate 1): a small model through DSPy, with schema-bound JSON; or the embedding check on tei-embed, with [ADR-0025](../docs/adr/0025-cpu-classifier-fallbacks-and-uncalibrated-models.md)'s rules.
2. **Embed** the search query on tei-embed.
3. **Search** Postgres: vector top 20 (`halfvec`, HNSW) and full-text top 20 (the `simple` dictionary), merged by reciprocal rank fusion.
4. **Rerank** on tei-rerank, and keep up to 5 sources within 2,500 tokens.
5. **Answer** (Gate 3): stream through LiteLLM, holding back the first 16 tokens to catch the abstain token.

Every turn runs every step, whatever the classifier decides, so that runs compare like with like.

**Stopping early.** Each level of such a run goes through every sample once, unless `--turns` says otherwise. A sample's prompt then comes round again only after every other sample's, long after a runtime's prompt cache has let it go.

- **`--classify-only`** stops each turn after Gate 1, for the classifier bake-off (#14). The run neither loads the knowledge base nor uses the answer model, so the classifier is the only model in memory.
- **`--retrieve-only`** stops each turn after the rerank, for the retrieval bake-off (#15). The search query is the configured classifier's, as in a full turn. With the embedding check as the classifier, no language model runs at all.

**Some samples only.** `--samples on-topic` runs only the on-topic questions, answerable or not, and `--samples answerable` only the answerable ones, which are all recall@5 scores. A retrieval run then takes a third of the time.

**Prompts.** They follow Gate 1 and Gate 3 and fill each budget:
- Filler exchanges stand in for earlier turns.
- The budgets default to the PRD's and are parameters, so CPU installs can try lower ones.
- Ollama cannot count tokens, so a run first measures how each model counts them, from a sample text per script.

**Concurrency.** At concurrency *n*, *n* simulated customers each ask one question after another. Meanwhile the harness samples every container's memory and CPU twice a second.

**One pass through the samples.** A run, warm-up included, goes through the samples once and then round again, rather than restarting at each level. Otherwise a level would resend prompts that Ollama's prompt cache still holds, and look faster than it is. Keep the turns per level at or below the number of samples for the same reason.

## Running it

Start the stack first: from the repository root, `docker compose up --build --detach --wait`. Then, from this directory:

```sh
docker compose run --rm bench run configs/dev.toml
docker compose run --rm bench run configs/dev.toml --dataset data/gov-uk
docker compose run --rm bench run configs/dev.toml --concurrency 1,2,4 --turns 20 --label quiet-hour
docker compose run --rm bench run configs/dev-embedding.toml --classify-only
docker compose run --rm bench run configs/dev-embedding.toml --retrieve-only
docker compose run --rm bench judge results/A.json
docker compose run --rm bench score results/A.json
docker compose run --rm bench compare results/A.json results/B.json
```

A run uses one business's dataset, as an install serves one business ([ADR-0006](../docs/adr/0006-one-install-per-business.md)): the configuration's, or `--dataset`'s. Switching datasets reloads the knowledge base.

The harness runs in a container on the stack's internal network, where it reaches TEI, Ollama and Postgres as the API does.

- **The Docker socket.** The container reads each container's memory and CPU through it. It also reads the stack's settings from the api container: where Ollama is, and the Postgres password. The socket gives root on the host, so run the harness only where you would run `docker` yourself. It is never part of an install.
- **Code changes.** The container uses this directory's code, configurations and data, so edits need no rebuild. Dependency changes do: `docker compose build`.
- **On a server**, the same commands work without code changes. Copy this directory to the server, start the install, and run them there.
  - The stack's Compose project must be `support-chatbot`, as the install bundle names it.
  - The harness competes with the stack for CPU, but lightly: it mostly waits on the services.

### On the vendor's Mac

`configs/dev.toml` uses the Mac's own Ollama, through `SC_OLLAMA_URL` in the root `.env`, with its cloud models. TEI runs the development models from `deploy/dev.env`.

These runs check the wiring and the prompts. Cloud models say nothing about CPU speed, and the development models say little about retrieval quality. Send cloud models only synthetic or public data, such as `data/`.

A run takes about a minute. `configs/dev-embedding.toml` runs the embedding check instead of a small model.

## Configurations

One TOML file per model configuration, in `configs/`. `configs/bake-offs/` holds the bake-offs' own, and `reports/` their reports, such as [round 1](reports/2026-10-11-bake-offs-round-1.md). Here are the fields, with their defaults:

```toml
name = "cpu-4b"                       # names the results

[classifier]
mode = "model"                        # or "embedding", the embedding check on tei-embed
model = "ollama_chat/qwen3:1.7b"      # a LiteLLM model; Ollama's start with ollama_chat/
reasoning_effort = "none"             # turns reasoning off; gpt-oss takes low, medium or high
# api_base: where the model is served; Ollama models default to the stack's Ollama
# margin = 0.05: the embedding check's on_topic bias

[answer]
model = "ollama_chat/qwen3:4b"
reasoning_effort = "none"
# temperature = 0.3: Gate 3 allows at most 0.3

[budgets]                             # the PRD's, in tokens
classify_in = 1200
classify_out = 120
classify_history = 600                # the last 3 exchanges
answer_in = 4500
answer_out = 400
answer_history = 1500                 # the last 6 turns
sources = 2500                        # at most max_sources = 5 chunks
fill = true                           # false: only each sample's own history

[run]                                 # the command line can override all three
concurrency = [1]
turns = 20                            # per level; p95 means little below about 20
warmup = 2                            # turns before the first level, left out

[data]
dataset = "data/acme-pay"             # one business's directory; --dataset overrides it

[stack]
project = "support-chatbot"
extra_containers = []                 # also measure these containers, outside the project
```

An external provider's model takes its API key from the environment, which `docker compose run` passes through by name: `docker compose run --rm -e OPENAI_API_KEY bench run configs/external.toml`. Send it only synthetic or public data, such as `data/`.

The embedding model and the reranker are whatever the stack's TEI containers serve. The vendor sets them in the install's environment ([ADR-0030](../docs/adr/0030-vendor-sets-local-embedding-and-rerank-models.md)), and the results name them. To compare pairings, restart TEI with another `SC_EMBEDDING_MODEL` or `SC_RERANK_MODEL` and run `--retrieve-only`: a new embedding model changes the knowledge base's fingerprint, and the run reloads it.

The harness gives each Ollama model a context window (`num_ctx`) that fits its prompts and replies. A model that both classifies and answers gets one size for both, because Ollama reloads a model when the size changes.

## Results

Each run writes two files to `results/`, which git ignores; commit a run only on purpose.

- **`<time>-<name>.json`** holds everything: the host, the dataset, the models, the calibration, the budgets, and per concurrency level:
  - the statistics;
  - each container's peak memory and its mean and peak CPU;
  - every turn, with its timings, tokens, category, search query, the reranker's top 5 chunks, the prompt's sources, and the answer;
  - the scores (below).

  `judge` adds its verdicts on the answers (below).
- **`<time>-<name>.md`** is the summary:
  - Gate 1's scores against the release gates (below);
  - p50 and p95 per step;
  - the first visible token, end to end, which is what the customer waits for;
  - tokens, and the answer's tokens per second;
  - peak memory and CPU per container.

Token counts are the models' own. Prompts are built to estimates calibrated on the run's own text, which land within about 5% of the models' counts. A prompt can therefore end a little under its budget or, rarely, a little over it.

With the PRD's part caps, an answer prompt reaches about 4,300 tokens with a short customer message: about 250 fixed, 2,500 of sources and 1,500 of history. The 4,500 total binds only for a long message, or when the total is set lower than the parts.

PR #21 has the first numbers: the Mac with cloud models, and CI's x86-64 runner with Qwen2.5 0.5B.

### Gate 1's scores

Every run scores each sample's first turn against the dataset's labels, per group and pooled, and sets each rate beside its release gate:

- **Off-topic messages declined** (≥ 95%) and **on-topic messages wrongly declined** (≤ 2%). A message is declined when it gets a template reply: off_topic or smalltalk, as neither answers it.
- **Requests for a person detected** (≥ 98%). With 25 to 30 requests per group, one miss puts a group below 98%, so read the pooled rate beside each group's.
- **The right reply** for every sample, and for each case on its own: turns that need the earlier messages, a yes after an offer of a person, and injections.
- **What each category was given**, pooled: the confusion table.
- **Gate 1's p50 and p95 per group**, at each concurrency level.

A turn that failed counts against every gate: it neither declined nor handed off. Each rate shows its counts, such as 97.3% (146/150), since a group's rate rests on few samples.

### Recall@5

A run whose turns searched also scores retrieval, over each answerable question's first turn, per group and pooled:

- **Retrieval recall@5** (≥ 90%): the sources found among the reranker's top 5 chunks, of all the sources the questions need. A source is found when a chunk holds its section, or a section below it, in any of its copies, such as its translation.
- **Questions with every source** in the top 5.
- **Sources in the answer prompt:** found among the chunks the prompt took, which fit its sources budget, 2,500 tokens by default. The last of them may be cut to fit, and it still counts. Retrieve-only runs build no prompt, so they leave this out.

A turn that failed before the rerank found nothing. The knowledge bases are small, at 29 to 202 chunks, so recall reads higher than it would over an install's thousands; comparisons between pairings still hold.

### Answers

A run that answered scores Gate 3, over each on-topic question's first turn, per group and pooled. Code checks what it can by itself:

- **Unanswerable questions answered instead of handed off** (≤ 10%): the answer model gave an answer where it should have abstained. A turn that failed counts against it too, as it handed nothing off.
- **Answerable questions abstained on.**
- **Citations:** answers citing a source that holds the expected facts, and answers citing a number the prompt had no source for.

**`bench judge results/A.json`** adds what takes reading. A judge model reads each answer beside what the answer model was given, and the facts a correct answer states. That is the business's description and the prompt's sources, rebuilt from the dataset, with the last one cut where the prompt cut it. It gives:

- a verdict on each expected fact: stated, contradicted or missing;
- the claims no source supports;
- the reply's language: en, fr, ar (Modern Standard Arabic), darija, or other.

Those give two more gates: **answer correctness** (≥ 85%), where every fact is stated and none contradicted, and **answers with unsupported claims** (≤ 3%). The summary also scores **replies in the customer's language**, where a Darija message takes Darija or Modern Standard Arabic, in Arabic script ([ADR-0035](../docs/adr/0035-darija-replies-in-arabic-script.md)), and counts the replies' languages per group. It is a score, not a release gate.

- **The judge** defaults to `gpt-oss:120b` on Ollama's cloud, from another family than the development answer model. Pick another with `--judge`, any LiteLLM model. Send a cloud judge only synthetic or public data, such as `data/`.
- **Output:** the judge's output is bound to a schema, with one retry after an error or a bad reply, as Gate 1's is. An answer it still fails on is named in the results, and left out of the judge's gates. If it fails on every answer, the results stay as they were.
- **Where the verdicts go:** into the results file, with the judge and the date, and the summary is written again.
- **A changed dataset:** `judge` refuses a run whose dataset's knowledge base has changed since, as the judge would then see other sources than the answer model did.
- **Judge it again:** run `judge` again, with the same judge or another, to replace the verdicts. Do so after a review changes a sample's facts: `score` leaves out a verdict whose facts no longer match the sample's.

### Scoring again

`score` scores a saved run again against the dataset's current labels, with its judge's verdicts if any, for instance after a review corrects a category. Turns whose samples the dataset no longer has are left out and named.

`compare` prints several runs side by side, matched by concurrency level, with Gate 1's rates and recall@5 per group for runs that have scores. It leaves out rows that no run has. `METHOD_VERSION` in `bench/__init__.py` changes when results stop being comparable with earlier ones.

## Data

The samples the bake-offs score against (#13), one directory per business in `data/`. The test set comes from the live beta ([ADR-0022](../docs/adr/0022-eval-data-from-the-live-beta.md)); these vendor-made samples only choose M0's defaults.

| Dataset | Business | Knowledge base | Samples |
| --- | --- | --- | --- |
| `acme-pay` | A fictional Algerian fintech and digital-goods business, like the beta's | 11 help articles, each in French and Arabic | Arabic, and Darija in Latin and in Arabic script; a few in French and English |
| `gov-uk` | GOV.UK's driving and vehicles pages, from DVLA | 40 public pages, under the Open Government Licence v3.0 | English |
| `service-public` | Service-Public.fr's money and consumer guides | 32 public pages, under Licence Ouverte 2.0 | French |

The fictional business tests whether a model keeps to its sources, since no model knows its facts. The public pages test models that may already know the answers, and come with real pages' untidy markup.

Each directory holds:

- **`turns.toml`:** the business's name and description, then turns. Each turn has an `id`, a `language` (en, fr, ar or darija), a `message` and Gate 1's expected `category`. It may have an `interface_language`, a `history`, `offered_person`, `cases` and a `note`.
  - An on-topic turn expects an `answer`, with the `facts` a correct answer states (in English) and its `sources`, or a `handoff` when the knowledge base cannot answer it. A fact states only what the question asks: delays, fees or conditions nobody asked about don't belong, unless the customer reports a problem and the fact is what to do (#41).
  - A source reads `file.md#Heading > Below it`, or `file.md` for anywhere in the document. ` | ` separates other places that state the same facts, such as a translation.
  - `cases` marks what else a turn tests: `needs_history`, `yes_after_offer` or `injection`.
  - Darija is Algerian Darija, in either script, never Moroccan: *nheb* or *7ab*, not *bghit*; *dorka*, not *daba*; *kach*, not *chi* (#43).
- **`kb/<language>-<topic>.md`:** the knowledge base, in Markdown.
- **`sources.toml`:** each document's origin and license. Top-level keys apply to every document; a `[[documents]]` entry sets them for one file.
- **`examples.toml`:** the embedding check's example phrases per category, and its words for yes. None may repeat a turn's message.

Results are reported per group: en, fr, ar, darija-latin and darija-arabic. A Darija message's group is the script most of its letters are in; one without letters goes by the widget's language.

The loader checks each dataset when a run starts: every turn's rules, every source against the documents' headings, every document's origin and license, and the example phrases against the turns. `tests/test_committed_data.py` checks #13's minimums on the committed data: at least 25 samples per category and 30 answerable and 10 unanswerable questions in each group, plus cases that need the history, a yes after an offer of a person, and injections.

**The public pages** are fetched with trafilatura, as KB-8's web import will: `uv run data/fetch.py data/gov-uk`. Pages change, so review the diff before committing: questions and their sources may need to follow. Service-Public.fr's pages show what that import will meet:
- Glossary tooltips leave ": titleContent" in the text.
- Headings skip levels, and some text lands under a heading it does not belong to.
- Each page ends with feedback-form sections.

Sources name the section that text lands in after chunking, even when its heading reads oddly.

## Development

- In this directory: `uv run pytest`, `uv run ruff check`, `uv run ruff format` and `uv run mypy`.
- The tests marked `stack` need a running stack, and run in the container: `docker compose run --rm --entrypoint pytest bench -m stack`.
- CI's `bench.yml` runs both when this directory changes, then a short run on x86-64 with Qwen2.5 0.5B in the stack's own Ollama. A CI run shows its summaries on the run's page, and keeps its results files as the `bench-results` artifact for 30 days.

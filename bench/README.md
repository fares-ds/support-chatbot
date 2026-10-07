# Benchmark harness

The M0 benchmark (#12). It times the AI pipeline end to end against a running stack, so that M0 can set the CPU numbers the PRD leaves open: latency targets, the classifier mode, default models, prompt budgets and minimum specs ([ADR-0011](../docs/adr/0011-cpu-first-models.md), [ADR-0024](../docs/adr/0024-stack-review-corrections.md)). It needs only the stack, not the product's code, and M3 can run it again against the real pipeline.

## What a turn does

Each turn runs Flow B's steps, as a real turn would:

1. **Classify** (Gate 1): a small model through DSPy, with schema-bound JSON; or the embedding check on tei-embed, with [ADR-0025](../docs/adr/0025-cpu-classifier-fallbacks-and-uncalibrated-models.md)'s rules.
2. **Embed** the search query on tei-embed.
3. **Search** Postgres: vector top 20 (`halfvec`, HNSW) and full-text top 20 (the `simple` dictionary), merged by reciprocal rank fusion.
4. **Rerank** on tei-rerank, and keep up to 5 sources within 2,500 tokens.
5. **Answer** (Gate 3): stream through LiteLLM, holding back the first 16 tokens to catch the abstain token.

Every turn runs every step, whatever the classifier decides, so that runs compare like with like.

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
docker compose run --rm bench run configs/dev.toml --concurrency 1,2,4 --turns 20 --label quiet-hour
docker compose run --rm bench compare results/A.json results/B.json
```

The harness runs in a container on the stack's internal network, where it reaches TEI, Ollama and Postgres as the API does.

- **The Docker socket.** The container reads each container's memory and CPU through it. It also reads the stack's settings from the api container: where Ollama is, and the Postgres password. The socket gives root on the host, so run the harness only where you would run `docker` yourself. It is never part of an install.
- **Code changes.** The container uses this directory's code, configurations and data, so edits need no rebuild. Dependency changes do: `docker compose build`.
- **On a server**, the same commands work without code changes. Copy this directory to the server, start the install, and run them there.
  - The stack's Compose project must be `support-chatbot`, as the install bundle names it.
  - The harness competes with the stack for CPU, but lightly: it mostly waits on the services.

### On the vendor's Mac

`configs/dev.toml` uses the Mac's own Ollama, through `SC_OLLAMA_URL` in the root `.env`, with its cloud models. TEI runs the development models from `deploy/dev.env`.

These runs check the wiring and the prompts. Cloud models say nothing about CPU speed, and the development models say little about retrieval quality. Send only synthetic data, such as `data/`, to cloud models.

A run takes about a minute. `configs/dev-embedding.toml` runs the embedding check instead of a small model.

## Configurations

One TOML file per model configuration, in `configs/`. Here are the fields, with their defaults:

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

[stack]
project = "support-chatbot"
extra_containers = []                 # also measure these containers, outside the project
```

An external provider's model takes its API key from the environment, which `docker compose run` passes through by name: `docker compose run --rm -e OPENAI_API_KEY bench run configs/external.toml`. Send it only synthetic data, such as `data/`.

The embedding model and the reranker are whatever the stack's TEI containers serve. The vendor sets them in the install's environment ([ADR-0030](../docs/adr/0030-vendor-sets-local-embedding-and-rerank-models.md)), and the results name them.

The harness gives each Ollama model a context window (`num_ctx`) that fits its prompts and replies. A model that both classifies and answers gets one size for both, because Ollama reloads a model when the size changes.

## Results

Each run writes two files to `results/`, which git ignores; commit a run only on purpose.

- **`<time>-<name>.json`** holds everything: the host, the models, the calibration, the budgets, and per concurrency level:
  - the statistics;
  - each container's peak memory and its mean and peak CPU;
  - every turn, with its timings, tokens, category, search query, sources and answer.

  A later scorer can judge the classifier and the answers from it (#14, #15).
- **`<time>-<name>.md`** is the summary:
  - p50 and p95 per step;
  - the first visible token, end to end, which is what the customer waits for;
  - tokens, and the answer's tokens per second;
  - peak memory and CPU per container.

Token counts are the models' own. Prompts are built to estimates calibrated on the run's own text, which land within about 5% of the models' counts. A prompt can therefore end a little under its budget or, rarely, a little over it.

With the PRD's part caps, an answer prompt reaches about 4,300 tokens with a short customer message: about 250 fixed, 2,500 of sources and 1,500 of history. The 4,500 total binds only for a long message, or when the total is set lower than the parts.

`compare` prints several runs side by side, matched by concurrency level. `METHOD_VERSION` in `bench/__init__.py` changes when results stop being comparable with earlier ones.

## Data

`data/` holds placeholders written for #12 about a fictional operator, Acme Mobile:

- a knowledge base of 8 documents in English, French and Arabic, which make 19 chunks;
- 20 turns in English, French, Arabic and Darija (in Latin and in Arabic script);
- the embedding check's example phrases.

The Arabic and Darija ones are unreviewed. #13 replaces them with reviewed datasets.

## Development

- In this directory: `uv run pytest`, `uv run ruff check`, `uv run ruff format` and `uv run mypy`.
- The tests marked `stack` need a running stack, and run in the container: `docker compose run --rm --entrypoint pytest bench -m stack`.
- CI's `bench.yml` runs both when this directory changes, then a short run on x86-64 with Qwen2.5 0.5B in the stack's own Ollama.

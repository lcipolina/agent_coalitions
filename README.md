# Capability-Search-Based Delegation System for Multi-Agent Collaboration

> An MVP for assembling specialist agent teams from a skill marketplace, then having them collaborate end-to-end on a complex brief — all on MongoDB Atlas.
>
> *Conceptual outputs produced by an experimental multi-agent system. Not certified engineering. Not for production.*

## What this is

A single Python process that takes a prompt for a long and complex tasks, decomposes it into a DAG of subtasks, runs MongoDB Atlas Vector Search + pairwise-complementarity team formation to assign 1–3 agents per subtask, lets each team collaborate on a Mongo-backed message log coordinated by a marshal LLM, and synthesises the result into a structured proposal with visualisations and a deterministic validation card.

**MongoDB Atlas is live.** All thirteen domain collections and the Atlas Vector Search index are real and exercised on every run. The only thing that can be mocked is the LLM layer (chat + embeddings); when mocked, Atlas Vector Search still runs end-to-end — only the query vector changes from an OpenAI embedding to a deterministic SHA-256-seeded pseudo-embedding. Mock mode is the default for the live demo because it finishes a full pipeline run in under five seconds and never depends on network weather.

For the system design, the rationale behind every interesting choice (skill–agent split, team value formula, communication-forum protocol, validation ordering, reputation weighting), and the full repository layout, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The product contract is in [docs/MVP_DESIGN.md](docs/MVP_DESIGN.md), the cooperative-game-theory background in [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md), the matching-pipeline walkthrough in [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md), the 5-minute pitch script in [docs/PITCH.md](docs/PITCH.md), and the post-MVP backlog in [docs/TODO.md](docs/TODO.md).

---

## Prerequisites

- **macOS / Linux / WSL** (only tested on macOS for now).
- **Conda or Miniconda** installed (`conda --version` should print something).
- **MongoDB Atlas** cluster (free tier is fine) with **Atlas Search** enabled.
- **OpenAI API key** (or run in mock mode without one — see below).
- Git.

---

## Setting up the environment (one-time, per machine)

The conda env is the source of truth. Recreate it on a clean machine with:

```bash
git clone <this repo>
cd Hackathon_MongoDB

# 1. Create the conda env (takes 3–8 minutes the first time).
conda env create -f environment.yml

# 2. Activate it.
conda activate coalitions

# 3. Verify the install.
python -c "import pymongo, openai, streamlit, plotly, dotenv, langgraph, tiktoken; print('OK')"
```


A `requirements.txt` mirror is provided for non-conda users (`python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`), but the conda env remains the source of truth.

### Configuring secrets

```bash
cp .env.example .env
# Then edit .env with your real MongoDB URI and OpenAI key.
```

`.env` is gitignored. Never commit it.

---

## Running

> **Mock mode is the default.** It uses no API calls and a full pipeline run
> finishes in under 5 seconds. This is what we use for the live demo.

### Live demo (Streamlit UI)

```bash
conda activate coalitions
streamlit run app.py
```

Then, in the browser:

1. Click **🚀 Run pipeline** (a default prompt is pre-filled).
2. Watch the live progress panel: stage progress bar, per-subtask
   skills picked from vector search, agents assigned by greedy
   set-cover with their solo scores, and who paired with whom.
3. When the run finishes, the 10 result tabs populate from MongoDB:
   **🌳 DAG**, **👥 Teams**, **💬 Council**, **✅ Validation**,
   **💶 Cost**, **🎨 Rendering**, **📄 Report**,
   **📈 Reputation**, **🕸️ Workflow**, **🍃 MongoDB**.
4. Click **🔁 Replay current** to re-read the run from MongoDB only
   (zero LLM calls, asserted by the orchestrator).
5. The sidebar shows the 10 most recent runs — click any to switch.

### CLI

```bash
python -m src.run --prompt "<your brief here>"
python -m src.run --replay <run_id>
```

### Tests

```bash
pytest tests/ -v
```

### Real LLM mode (used for the demo video, not the live run)

Set `USE_MOCK_LLM=false` in `.env`. The same code path applies; the
only difference is `src.llm.openai_client` routes to OpenAI (or to
OpenRouter if `OPENAI_BASE_URL` is set). Embeddings always go to
OpenAI proper via `OPENAI_EMBEDDING_API_KEY`.

### Replay-mode lockdown (publishing the demo without an OpenAI key)

The published build forces `USE_MOCK_LLM=true` and locks the prompt
input to a small dropdown of curated prompts. Captured real LLM
responses are read from `data/llm_replay_cache.json` so the pipeline
looks identical to a real run for those prompts; unknown payloads fall
back to the deterministic stubs in `src/llm/mock.py`.

To refresh the captured cache:

```bash
# 1. Run each demo prompt once in real mode (with USE_LLM_CACHE=true,
#    which is the default). MongoDB's llm_cache collection captures
#    every chat + embed call.
USE_MOCK_LLM=false python -m src.run --prompt "<demo prompt 1>"
USE_MOCK_LLM=false python -m src.run --prompt "<demo prompt 2>"
USE_MOCK_LLM=false python -m src.run --prompt "<demo prompt 3>"

# 2. Export MongoDB llm_cache → data/llm_replay_cache.json (commit it).
python scripts/export_llm_cache.py
```

The Streamlit sidebar shows a "🔒 Replay mode" badge with the entry
count and export date so judges can see at a glance that no API calls
are being made.

---

## Checking the MongoDB cluster is alive

The Atlas free tier auto-pauses clusters after **60 days of inactivity**, and
free clusters can also be evicted after long quiet periods. If you suspect
the cluster has gone away (the deployed app shows
`pymongo.errors.ConfigurationError`, or the local pipeline times out), run the
health-check script:

```bash
conda run -n coalitions --no-capture-output python scripts/check_mongo.py
```

A healthy cluster prints, in order:

```
URI    : mongodb+srv://<user>:<redacted>@<your-cluster>/...
DB     : agent_coalitions
ping   : ok=1.0
colls  : 14 -> [agents, artifacts, assignments, coalition_messages, ...]
runs   : 180 documents
skills : 70 documents
vidx   : ok (search indexes: ['skills_embedding_vector'])
```

The script is in [scripts/check_mongo.py](scripts/check_mongo.py); exit code
is `0` when everything is healthy, non-zero on ping failure or missing
vector-search index. It's safe to wire into a `cron` job or a GitHub Action
if you want a daily heartbeat.

**If `ping` fails:**

- Sign in at https://cloud.mongodb.com → check the cluster card. If it shows
  *"Paused"*, click **Resume**. The free tier resumes in ~30 s.
- Verify **Network Access → IP Access List** still contains `0.0.0.0/0`
  (Streamlit Cloud has no fixed egress IPs) and your local IP if you're
  running locally.
- Verify the database user in **Database Access** still exists and has the
  right role (`readWriteAnyDatabase` or scoped to `agent_coalitions`).
- If the cluster has been **deleted**, restore from the data export under
  [data/skills_seed.json](data/skills_seed.json) plus
  [data/llm_replay_cache.json](data/llm_replay_cache.json) by re-running the
  seed script in [src/db/seed.py](src/db/seed.py). The replay cache means
  past run outputs aren't recoverable, but the demo can re-run any of the
  three locked-in prompts from scratch in mock mode.

**If `vidx` is `MISSING`:** the Atlas Vector Search index was dropped (Atlas
sometimes does this on cluster tier changes). Recreate it from
[src/db/indexes.py](src/db/indexes.py) — the constant
`VECTOR_INDEX_DEFINITION` has the JSON the script POSTs to the Atlas Admin
API.

---

## Deploying to Streamlit Community Cloud

The app is ready to deploy from this public GitHub repo to
[share.streamlit.io](https://share.streamlit.io) — no code changes needed.

1. **Sign in** at [share.streamlit.io](https://share.streamlit.io) with the
   GitHub account that owns this repo.
2. **New app** → pick `lcipolina/agent_coalitions`, branch `master`, main file
   `app.py`. Python version is read from [runtime.txt](runtime.txt) (3.11).
   Dependencies are read from [requirements.txt](requirements.txt).
3. **Advanced settings → Secrets**: paste the contents of
   [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) with
   real values. Only `MONGODB_URI` and `MONGODB_DB` are required — the
   replay cache (`data/llm_replay_cache.json`) handles every demo prompt
   without OpenAI calls.
4. **MongoDB Atlas → Network Access**: add `0.0.0.0/0` to the IP allow-list
   (Streamlit Cloud has no fixed egress IPs). Use a read-mostly user with a
   strong password, since the cluster is now reachable from anywhere.
5. **Deploy**. First build takes 2–3 minutes; subsequent pushes to `master`
   redeploy automatically.

The bridge from `st.secrets` → `os.environ` happens at the top of
[app.py](app.py) before `src.core.config` is imported, so the same
pydantic-settings code path is used locally (`.env`) and in the cloud
(Secrets panel).

---

## Repository layout

See [docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md#11-repository-layout). The same document also contains the system-level design rationale behind every non-trivial choice in this codebase.

---

# Agent Coalitions

> Capability-search-based delegation system for multi-agent collaboration. Built for the **MongoDB London hackathon — Multi-Agent Collaboration track**.
>
> *Conceptual design produced by an experimental multi-agent system. Not certified engineering. Not for construction.*

## What this is

A single Python process that takes a user brief (e.g., *"design a 2 km bridge for 50 cars/h"*), decomposes it into a DAG of subtasks, runs MongoDB Atlas Vector Search + pairwise-complementarity coalition formation to assign 1–3 agents per subtask, lets each coalition collaborate on a Mongo-backed blackboard with a marshal LLM, and synthesises the result into a government-bid-style proposal with two visualisations and a deterministic validation card.

See `MVP_DESIGN.md` for the full spec (it is the contract). See `PLAN.md` for the executable plan. See `GAME_THEORY_PRIMER.md` for the cooperative-game-theory background. See `TODO.md` for the post-hackathon backlog.

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

1. Click **🚀 Run pipeline** (the default prompt is pre-filled).
2. Watch the live progress panel: stage progress bar, per-subtask
   skills picked from vector search, agents assigned by greedy
   set-cover with their solo scores, and who paired with whom.
3. When the run finishes, the 8 result tabs populate from MongoDB:
   **DAG**, **Coalitions**, **Blackboard**, **Validation**, **Cost**,
   **Bridge** (elevation plot), **Report**, **Reputation**.
4. Click **🔁 Replay current** to re-read the run from MongoDB only
   (zero LLM calls, asserted by the orchestrator).
5. The sidebar shows the 10 most recent runs — click any to switch.

### CLI

```bash
python -m src.run --prompt "design a 2 km bridge for 50 cars/h"
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

---

## Repository layout

```
app.py                       # Streamlit UI (run with: streamlit run app.py)
cost_model.json              # EUR unit costs for the surveyor
src/
  config.py                  # pydantic-settings; reads .env
  matching.py                # Atlas $vectorSearch + cosine fallback
  tokens.py                  # tiktoken count + truncate (200-tok cap)
  progress.py                # progress event bus for live UI
  run.py                     # CLI entrypoint
  llm/
    mock.py                  # deterministic embeddings + role-keyed chat
    openai_client.py         # real-mode wrapper; routes by USE_MOCK_LLM
    prompts.py               # Jinja2 template loader (render(name, **ctx))
  prompts/                   # *.j2 templates — one per LLM role
  db/
    client.py, indexes.py, writes.py, seed.py
  agents/
    coalitions.py            # rank-1 Shapley greedy coalition formation
    set_cover.py             # weighted greedy skill→agent set cover
    blackboard.py            # post / read coalition_messages
    marshal.py               # round 0 kickoff + round 2 reconcile
  pipeline/
    decomposer.py, execution.py, synthesis.py, validation.py,
    surveyor.py, reporter.py, reputation.py, orchestrator.py
  scripts/
    ingest_skills.py, ping_mongo.py, test_vector_search.py
tests/
  test_matching.py, test_coalitions.py, test_validation.py,
  test_e2e_mock.py           # full pipeline + replay invariants
```

---

## Build status

The project is built gate-by-gate per `PLAN.md`. Each gate corresponds to one git commit and has a single self-check.

| Gate | What | Status |
|---|---|---|
| G1 | Conda env reproducible | ✅ done |
| G2 | Config + secrets wiring | ✅ done |
| G3 | Mongo connectivity (13 collections + vector index) | ✅ done |
| G4 | Skills ingested (36 skills, 21 agents) | ✅ done |
| G5 | Atlas Vector Search live | ✅ done |
| G6 | Mock pipeline end-to-end (12/12 tests green) | ✅ done |
| G7 | Real-LLM pipeline end-to-end | deferred (used for demo video) |
| G8 | Streamlit UI with live progress + 8 tabs + bridge viz | ✅ done |
| G9 | Replay works (zero LLM calls asserted) | ✅ done |
| G10 | Reputation persists across runs | ✅ done |
| G11 | Demo script passes (≤90s) | pending |

---

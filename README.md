# Agent Coalitions

> Capability-search-based delegation system for multi-agent collaboration. Built for the **MongoDB London hackathon — Multi-Agent Collaboration track**.
>
> *Conceptual design produced by an experimental multi-agent system. Not certified engineering. Not for construction.*

## What this is

A single Python process that takes a user brief (e.g., *"design a 2 km bridge for 50 cars/h"*), decomposes it into a DAG of subtasks, runs MongoDB Atlas Vector Search + pairwise-complementarity coalition formation to assign 1–3 agents per subtask, lets each coalition collaborate on a Mongo-backed blackboard with a marshal LLM, and synthesises the result into a government-bid-style proposal with two visualisations and a deterministic validation card.

**MongoDB Atlas is live.** All thirteen domain collections and the Atlas Vector Search index are real and exercised on every run. The only thing that can be mocked is the LLM layer (chat + embeddings); when mocked, Atlas Vector Search still runs end-to-end — only the query vector changes from an OpenAI embedding to a deterministic SHA-256-seeded pseudo-embedding. Mock mode is the default for the live demo because it finishes a full pipeline run in under five seconds and never depends on network weather.

For the system design, the rationale behind every interesting choice (skill–agent split, coalition value formula, blackboard protocol, validation ordering, reputation weighting), and the full repository layout, see [ARCHITECTURE.md](ARCHITECTURE.md). The product contract is in `MVP_DESIGN.md`, the executable plan in `PLAN.md`, the cooperative-game-theory background in `GAME_THEORY_PRIMER.md`, and the post-hackathon backlog in `TODO.md`.

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

See [ARCHITECTURE.md §10](ARCHITECTURE.md#10-repository-layout). The same document also contains the system-level design rationale behind every non-trivial choice in this codebase.

---

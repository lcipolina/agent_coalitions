# Capability-Search-Based Delegation System for Multi-Agent Collaboration

> An MVP for assembling specialist agent teams from a skill marketplace, then having them collaborate end-to-end on a complex brief — all on MongoDB Atlas.
>
> *Conceptual outputs produced by an experimental multi-agent system. Not certified engineering. Not for production.*

## What this is

A single Python process that takes a free-text brief, decomposes it into a DAG of subtasks, runs MongoDB Atlas Vector Search + pairwise-complementarity team formation to assign 1–3 agents per subtask, lets each team collaborate on a Mongo-backed message log coordinated by a marshal LLM, and synthesises the result into a structured proposal with visualisations and a deterministic validation card.

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
   **🌳 DAG**, **👥 Teams**, **💬 Agent comms**, **✅ Validation**,
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

---

## Repository layout

See [docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md#11-repository-layout). The same document also contains the system-level design rationale behind every non-trivial choice in this codebase.

---

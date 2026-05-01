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

> **Mock mode is the default.** It uses no API calls and runs end-to-end deterministically. Always works.

```bash
# CLI (will exist after gate G6):
python -m src.run --prompt "design a 2 km bridge for 50 cars/h"

# Streamlit UI (will exist after gate G8):
streamlit run src/ui/app.py
```

To use real OpenAI calls, set `USE_MOCK_LLM=false` in `.env`.

---

## Build status

The project is built gate-by-gate per `PLAN.md`. Each gate corresponds to one git commit and has a single self-check.

| Gate | What | Status |
|---|---|---|
| G1 | Conda env reproducible | in progress |
| G2 | Config + secrets wiring | pending |
| G3 | Mongo connectivity | pending |
| G4 | Skills ingested | pending |
| G5 | Vector search live | pending |
| G6 | Mock pipeline end-to-end | pending |
| G7 | Real-LLM pipeline end-to-end | pending |
| G8 | Streamlit renders | pending |
| G9 | Replay works | pending |
| G10 | Reputation persists | pending |
| G11 | Demo script passes | pending |

---

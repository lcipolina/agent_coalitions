# PLAN.md — Agent Coalitions MVP (1-day build)

> **Status:** Phase A complete (workflow.txt). All ambiguities in `MVP_DESIGN.md` have been resolved with the lead (2026-05-01). This document is the executable plan; the coding agent works through it commit-by-commit.
> **Source of truth:** `MVP_DESIGN.md` (with amendments listed in §3 below). `GAME_THEORY_PRIMER.md` is reference material.
> **Naming:** the word *"market"* is banned across code, UI, DB, and docs. We use *coalitions* / *delegation system*. Appendix A of `MVP_DESIGN.md` retains its historical discussion of why we don't use the word — that text is consistent with the ban and stays.

---

## TL;DR

Implement §9.2 of `MVP_DESIGN.md` as 11 ordered git commits aligned to gates **G1–G11** of §9.4. Each gate has a single concrete self-check; each commit maps onto one or more §9.3 acceptance criteria. Strategy:

1. Conda env reproducible (G1)
2. Config + secrets wiring (G2)
3. Mongo connectivity + indexes (G3)
4. Skills + agents seeded (G4)
5. Vector search live (G5)
6. **Mock-mode pipeline end-to-end (G6)** ← biggest commit
7. Real-LLM pipeline end-to-end (G7)
8. Streamlit + both visuals (G8)
9. Replay-from-Mongo with zero LLM calls (G9)
10. Reputation persistence across runs (G10)
11. Demo script narration ≤90 s (G11)

Mock mode is first-class throughout — the demo always works without OpenAI. LangGraph is the orchestrator with a pre-approved escape hatch to a plain function pipeline if it blocks G6 by more than ~30 min. Single coding agent, sequential, gate-by-gate.

---

## 1. File tree to be created

Workspace root (`/Users/lucia/Desktop/Hackathon_MongoDB`) **is** the project root — no nested `agent_market/` directory. The MongoDB database is renamed `agent_coalitions` (Q21).

```
.
├── README.md
├── PLAN.md                            # this file
├── MVP_DESIGN.md                      # contract (amended per §3 below)
├── GAME_THEORY_PRIMER.md              # reference
├── TODO.md                            # post-hackathon backlog
├── environment.yml                    # conda env (source of truth)
├── requirements.txt                   # mirror, optional
├── pyproject.toml                     # optional, src layout marker
├── .env.example                       # tracked
├── .env                               # gitignored
├── .gitignore
├── cost_model.json                    # surveyor unit costs
├── data/
│   └── skills_seed.json               # ~30–50 hand-authored skills (TODO: swap to 150 real)
├── src/
│   ├── __init__.py
│   ├── config.py                      # dotenv + typed settings; single load_dotenv()
│   ├── run.py                         # CLI entry: python -m src.run --prompt "..."
│   ├── orchestrator.py                # LangGraph wiring (with plain-fn fallback)
│   ├── decomposer.py
│   ├── matching.py                    # vector search + scoring
│   ├── coalitions.py                  # pairwise complementarity + greedy
│   ├── set_cover.py                   # skills → agents
│   ├── blackboard.py                  # post / read / render log
│   ├── marshal.py                     # kickoff + reconcile
│   ├── execution.py                   # per-subtask loop
│   ├── synthesis.py                   # design_specs builder
│   ├── validation.py                  # deterministic checks + LLM judge
│   ├── surveyor.py                    # cost computation + narrative
│   ├── reporter.py                    # final markdown bid doc
│   ├── reputation.py
│   ├── eval.py                        # §11.2 strategies (stretch)
│   ├── tokens.py                      # tiktoken-based summary truncation
│   ├── db/
│   │   ├── __init__.py
│   │   ├── client.py                  # singleton Mongo client
│   │   ├── indexes.py                 # idempotent indexes incl. vector index
│   │   ├── seed.py                    # load skills, synthesise agents
│   │   └── writes.py                  # helper that auto-inserts events row
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── openai_client.py           # chat + embeddings + image, with call counter
│   │   └── mock.py                    # deterministic mock for ALL roles incl. judge
│   ├── visualizer/
│   │   ├── __init__.py
│   │   ├── schematic_plotly.py
│   │   ├── architectural_svg.py
│   │   └── ai_render.py               # stretch G13
│   ├── prompts/
│   │   ├── decomposer.txt
│   │   ├── marshal_kickoff.txt
│   │   ├── marshal_reconcile.txt
│   │   ├── agent.txt
│   │   ├── synthesizer.txt
│   │   ├── surveyor_narrative.txt
│   │   ├── reporter.txt
│   │   └── judge.txt
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── ping_mongo.py              # G3
│   │   ├── ingest_skills.py           # G4
│   │   └── test_vector_search.py      # G5
│   └── ui/
│       ├── __init__.py
│       └── app.py                     # Streamlit, 8 tabs
└── tests/
    ├── __init__.py
    ├── test_matching.py
    ├── test_coalitions.py
    ├── test_validation.py
    └── test_e2e_mock.py               # full pipeline in mock mode
```

---

## 2. Ordered commits

Pre-flight commit #0 is the **spec snapshot** (workflow.txt guard rail). Every later commit corresponds to exactly one gate.

| # | Commit title | Files touched | §9.3 AC satisfied |
|---|---|---|---|
| 0 | `chore: spec snapshot` | `MVP_DESIGN.md` (amended per §3 below), `GAME_THEORY_PRIMER.md`, `PLAN.md`, `TODO.md`, `.gitignore`, `README.md` | guard rail (workflow.txt) |
| 1 | `gate G1: conda env reproducible` | `environment.yml`, `requirements.txt`, `pyproject.toml` (optional), `.env.example`, `README.md` (run section) | foundation for AC1 |
| 2 | `gate G2: config + secrets wiring` | `src/__init__.py`, `src/config.py` | foundation |
| 3 | `gate G3: mongo connectivity` | `src/db/client.py`, `src/db/indexes.py`, `src/db/writes.py`, `src/scripts/ping_mongo.py` | AC2, AC6 |
| 4 | `gate G4: skills ingested` | `data/skills_seed.json`, `src/db/seed.py`, `src/scripts/ingest_skills.py` | AC6 |
| 5 | `gate G5: vector search live` | `src/db/indexes.py` (vector index), `src/matching.py`, `src/llm/openai_client.py` (embeddings only), `src/scripts/test_vector_search.py` | AC1, AC6 |
| 6 | `gate G6: mock pipeline end-to-end` | `src/llm/mock.py`, `src/decomposer.py`, `src/coalitions.py`, `src/set_cover.py`, `src/blackboard.py`, `src/marshal.py`, `src/execution.py`, `src/synthesis.py`, `src/validation.py`, `src/surveyor.py`, `src/reporter.py`, `src/reputation.py`, `src/orchestrator.py` (LangGraph), `src/run.py`, `src/tokens.py`, `cost_model.json`, `src/prompts/*.txt`, `tests/test_matching.py`, `tests/test_coalitions.py`, `tests/test_validation.py`, `tests/test_e2e_mock.py` | **AC1, AC2, AC3, AC4, AC8** |
| 7 | `gate G7: real-LLM pipeline end-to-end` | `src/llm/openai_client.py` (chat + call counter), `src/decomposer.py`, `src/marshal.py`, `src/synthesis.py`, `src/surveyor.py`, `src/reporter.py`, `src/validation.py` (judge) | AC1, AC2, AC3, AC4, AC8 (real-mode) |
| 8 | `gate G8: streamlit renders` | `src/ui/app.py`, `src/visualizer/schematic_plotly.py`, `src/visualizer/architectural_svg.py` | **AC5, AC6, AC7, AC8** |
| 9 | `gate G9: replay works` | `src/ui/app.py` (Replay button), `src/orchestrator.py` (replay path), `src/llm/openai_client.py` (counter assertion) | **AC9** |
| 10 | `gate G10: reputation persists` | `src/reputation.py`, `src/run.py`, `src/eval.py` (cross-run snapshot helper) | **AC10** |
| 11 | `gate G11: demo script passes` | `README.md` (demo section), `src/ui/app.py` (polish), `src/visualizer/architectural_svg.py` (palette lock) | all of AC1–AC10 |

Stretch gates (only if ahead of schedule):

- **G12** — `src/eval.py` runs §11.2 A/B/C strategy comparison; results in Overview tab.
- **G13** — `src/visualizer/ai_render.py` + "Concept render" tab.

### Commit discipline (§9.1 #12)

- Repo is `git init`'d before commit #0.
- After each gate's self-check passes, run `git add -A && git commit -m "gate Gx: <name>"`.
- No `--force`, no `--no-verify`, no `git reset --hard` against shared history.
- `.env` gitignored; `.env.example` tracked.

---

## 3. Spec amendments (lead-confirmed 2026-05-01)

Apply all of these to `MVP_DESIGN.md` as part of commit #0 (spec snapshot). Bump §14 sign-off date to **2026-05-01**.

### 3.1 Naming (Q21)

The word "market" is banned in all current usage. Renames:

| Where | Old | New |
|---|---|---|
| MongoDB database name | `agent_market` | `agent_coalitions` |
| Project / repo display name | "Agent Market" | "Agent Coalitions" |
| Streamlit app title | "Agent Market" | "Agent Coalitions" |
| §6.1 tab #2 | "Agent Market" / "Assignment Ledger" | **"Assignments"** |
| §6.1 tab #3 | "Coalitions" | unchanged |
| §6.2 run button | "Run Agent Market" | **"Run Coalitions"** |
| §10 demo narration | "agent market" everywhere | "coalition pipeline" / "delegation system" |
| `MONGODB_DB` default in `.env.example` | `agent_market` | `agent_coalitions` |
| Appendix A | retains the *why we don't call it a market* discussion verbatim | unchanged |

### 3.2 Token cap (Q1)

Standardise on **200 tokens** for `subtask_outputs.summary`. Update §3.7 ("≤ 150 tokens" → "≤ 200 tokens"), example caption, and §10 narration ("150-token" → "200-token"). Truncation via `tiktoken` in `src/tokens.py`.

### 3.3 Algorithm definitions filled in (Q3, Q4, Q5)

Append to §4.2:

- `coverage(s, q) = clip(cosine(embedding(s), embedding(q)), 0, 1)`.
- `prior_reputation(s)` = min-max normalisation across the catalog of `0.5·log(1+installs) + 0.5·log(1+stars)`.
- The `γ` term reads `log(1+installs(s)) / log(1+max_installs_in_catalog)`, ∈ [0,1].

### 3.4 Default DAG fallback (Q6)

Add to §4.1 the canonical 7-subtask DAG used as decomposer fallback and by the mock decomposer:

| id | title | depends_on |
|---|---|---|
| T1 | Site & geometry (banks, span layout) | — |
| T2 | Load profile (live/dead/dynamic) | — |
| T3 | Material selection | T1, T2 |
| T4 | Structural system (truss / cable-stayed / arch) | T1, T2, T3 |
| T5 | Aesthetic & elevation guidance | T1, T4 |
| T6 | Validation prep (deterministic check inputs) | T3, T4 |
| T7 | Final synthesis brief | T1, T2, T3, T4, T5, T6 |

Each subtask's `required_capabilities` list will be authored in `src/decomposer.py` as a constant.

### 3.5 Marshal (Q7)

Single shared synthetic marshal, `agent_id = "agent_synthetic_marshal"`. Add a sentence to §13: *"For v1 there is exactly one marshal profile, used for every coalition."*

### 3.6 Validator checks (Q8)

§3.9 / §4.6 lists (minimum 5):

1. `span_to_depth_ratio` — ratio in [8, 18] passes; outside warns; <4 or >30 fails.
2. `support_count_consistency` — `len(span_layout) + 1 == n_supports` and `sum(span_lengths) ≈ total_length_m` within ±2%.
3. `live_load_arithmetic` — `design_live_load_kN_per_m × deck_width_m × total_length_m` reported; sanity range 1e3–1e6 kN.
4. `material_span_plausibility` — e.g., timber primary + max span >120 m → fail; concrete primary + max span >250 m → warn; steel + max span >1500 m → warn.
5. `lane_geometry` — `lanes × 3.5 m ≤ deck_width_m`.

### 3.7 Cost model (Q9)

`cost_model.json` (USD-equivalent values, currency tag `EUR` retained per spec):

```json
{
  "currency": "EUR",
  "structural_steel_per_tonne": 3500,
  "weathering_steel_per_tonne": 4000,
  "structural_concrete_per_m3": 180,
  "deck_slab_per_m2": 350,
  "pier_each": 150000,
  "abutment_each": 220000,
  "finishing_premium_pct": 10,
  "contingency_pct": 15
}
```

Quantity-take-off heuristics live in `src/surveyor.py`.

### 3.8 Schema additions (Q10, Q11)

- Add to `validation_results`: `judge_scores: [{subtask_id, clarity (0–10), completeness (0–10), consistency (0–10), rationale}]`.
- Add `runs.config = {seed: int, git_sha: str | null, use_mock_llm: bool}`. Remove the top-level `runs.use_mock_llm` (collapsed into `config`).
- `runs.summary_metrics.estimated_cost_eur` is a denormalised copy of `cost_estimates.total` (Q24).

### 3.9 Blackboard simplification (Q23)

Replace the priority-ordered serial loop in §4.5 with:

> Each coalition agent posts in **parallel**, seeing only the marshal kickoff and the upstream `subtask_outputs.summary` rows. Agents do **not** see each other's contributions in round 1. The marshal then reads all round-1 messages and reconciles. At most one revision round (round 3) follows if the marshal flags a single conflict.

This roughly halves intra-coalition tokens.

### 3.10 Replay verification (Q13)

`src/llm/openai_client.py` exposes a process-local call counter incremented on every chat/embedding/image call. The Replay button calls `openai_client.reset_counter()`, runs the replay path, and the orchestrator asserts `counter == 0` at end. An `events` row of `kind: "replay"` is the only stage event written.

### 3.11 Vector index creation (Q14)

`src/db/indexes.py` calls `database.create_search_index(...)` (Atlas Search admin). On failure (cluster lacks Search), log a clear error referencing the §3.1 vector-index requirement and continue (matching may fall back to in-Python cosine on the embedding column for development; G5 still requires Atlas vector search to pass).

### 3.12 Disclaimer string (Q22)

Canonical string, used verbatim in UI banner, every artifact, and final-report header:

> *Conceptual design produced by an experimental multi-agent system. Not certified engineering. Not for construction.*

### 3.13 Synthetic agent population (Q17)

20 agents total: **14 with 2 skills, 4 with 3 skills, 2 with 4 skills** (the polyvalent stars). Sampled from `skills_seed.json`. `created_at = updated_at =` ingestion time.

### 3.14 LangGraph (Q20)

Use LangGraph for the orchestrator. **Escape hatch:** if LangGraph wiring blocks gate G6 by more than ~30 minutes, the agent commits a plain function-based `src/orchestrator.py` and proceeds. This decision is pre-approved.

---

## 4. TODO.md (created at commit #0)

```markdown
# TODO — post-hackathon backlog

- [ ] Replace hand-authored data/skills_seed.json (~30–50 entries) with 150 real skills.sh entries.
- [ ] Replace mock LLM judge with real LLM judge in mock-mode parity tests.
- [ ] Run §11.2 strategy comparison (A/B/C) — implement gate G12.
- [ ] AI hero render (gate G13).
- [ ] Consider §A.4 truthful-reporting incentive mechanism (then we can legitimately call it a market).
- [ ] Tighten validator: include dynamic-load factor, fatigue check stub.
- [ ] Cache LLM responses in Mongo `llm_cache` collection (currently skipped).
```

---

## 5. Verification per gate

Run the listed self-check before committing. Stop and report on failure.

| Gate | Self-check |
|---|---|
| G1 | `conda env create -f environment.yml && conda activate agent-coalitions && python -c "import pymongo, openai, streamlit, plotly, dotenv, langgraph"` exits 0. |
| G2 | `cp .env.example .env`, fill secrets, then `python -c "from src.config import settings; print(settings.mongodb_db)"` prints `agent_coalitions`. `grep -RIn "sk-" src/` returns no hits outside `config.py`. |
| G3 | `python -m src.scripts.ping_mongo` connects, lists collections, creates the 11 collections + indexes (vector index attempted via `create_search_index`), exits 0. |
| G4 | `python -m src.scripts.ingest_skills` populates `skills` (~30–50) and `agents` (=20); printed counts match seed file. |
| G5 | `python -m src.scripts.test_vector_search "structural steel design"` returns ≥1 candidate with similarity score. |
| G6 | `USE_MOCK_LLM=true python -m src.run --prompt "design a 2 km bridge for 50 cars/h"` finishes <30 s; `subtask_outputs` non-empty for every subtask; ≥12 rows in `coalition_messages`; every pipeline stage has ≥1 `events` row; every summary ≤200 tokens (`tiktoken`-counted). `pytest tests/` green. |
| G7 | Same with `USE_MOCK_LLM=false`; finishes <5 min; same invariants. |
| G8 | `streamlit run src/ui/app.py` opens; clicking *Run Coalitions* with the default prompt populates all 8 tabs without errors; both visuals render; chat-style log visible in Coalitions tab. |
| G9 | After a finished run, set `OPENAI_API_KEY=invalid`, click *Replay from MongoDB* — all tabs repopulate; orchestrator asserts `openai_client.call_counter == 0`. |
| G10 | Run G6 prompt twice; `db.agents.find({}, {agent_id:1, reputation:1})` shows ≥3 reputations differ vs first run. |
| G11 | Stopwatch the §10 narration end-to-end while clicking through; ≤90 s without manual fixups. |

---

## 6. Decisions & assumptions

- **Orchestrator:** LangGraph with pre-approved escape hatch to plain functions if it blocks G6.
- **Single coding agent**, sequential, gate-by-gate. Each gate is an independent rewind point.
- **Mock mode is the development default** through Phases 1–5; real LLMs only at G7.
- Workspace root is the project root; no nested `agent_market/` dir; DB renamed `agent_coalitions`.
- AI hero render and §11.2 strategy comparison are **explicit stretch** (G12 / G13) — not part of definition-of-done.
- Conda `environment.yml` is source of truth; `requirements.txt` is a convenience mirror.
- Tests scope: the four files in §8 are authoritative — minimal asserts, not exhaustive.
- Token counting via `tiktoken`.

## 7. Out of scope

- Distributed agent runtimes / MCP / A2A protocols.
- FEA, CAD, real engineering certification, AR/VR.
- Exact Shapley computation.
- Authentication, rate limiting, deployment scripts, multi-tenant.
- Any tests beyond the four listed in `MVP_DESIGN.md` §8.
- LLM response caching (`llm_cache` collection).
- Bidding LLM calls or strategic agent behaviour (Appendix A).

---

## 8. Hand-off

Phase A (planning) is complete. On user "go", switch to **execute mode** (Phase B per workflow.txt):

1. Apply the §3 amendments to `MVP_DESIGN.md` and create `TODO.md`.
2. `git init && git add -A && git commit -m "chore: spec snapshot"` (commit #0).
3. Walk gates G1 → G11 in order. After each gate's self-check passes, commit with the prescribed message. Stop and ask if any spec turns out wrong.

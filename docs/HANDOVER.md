# Handover — Agent Coalitions / Bridge Studio

**Date:** May 2, 2026
**Repo:** `/Users/lucia/Desktop/Hackathon_MongoDB`
**Branches:**
- `master` — function-pipeline orchestrator. Working demo. Last commit: `4016e12 docs: add HANDOVER, drop truthful-reporting/market-defensibility line, doc updates`.
- `langgraph` — parallel LangGraph orchestrator behind the `USE_LANGGRAPH` flag (default OFF). Switchable at runtime from the Streamlit sidebar. Both backends produce byte-identical MongoDB rows. See [docs/LANGGRAPH.md](LANGGRAPH.md). Last commit: `208111d feat(langgraph): visible UI integration`.
**Hackathon:** [MongoDB London — Multi-Agent Collaboration track](https://cerebralvalley.ai/e/mongo-db-london-hackathon/details).

This document is for the **next coding agent** picking up the project. It is deliberately concrete. Read it top to bottom before changing anything.

---

## 1. What this project is

A working demo of a **MongoDB-Atlas-backed multi-agent task market** for conceptual design. The user types a prompt (default: design a pedestrian bridge across a 40 m river); the system decomposes it into subtasks, matches each subtask to a small **coalition of agents** drawn from a fixed pool, runs a 3-round blackboard collaboration, validates the synthesised spec, renders 3D geometry, and writes a Markdown report. **MongoDB Atlas is the shared market ledger, context store, coordination memory, and audit trail** — that is the pitch.

The hackathon premises (verbatim from `agent_market_mvp_implementation_brief.docx`):

> Multi-Agent Collaboration. Develop a multi-agent system in which specialized agents explore, assign tasks, and communicate with one another, using MongoDB to organize and oversee contexts. How do agents convey their skills, identify suitable peers for a sub-task, share context effectively within token limits, and perform intricate tasks resulting from successful collaborations?

Boss's critical steer (the reason the matching maths exists at all):

> One simplification will be to look at pairwise interactions (like induced sub-graphs games). OR some Shapley approximation… simple but I don't know how I would do it.

We implemented exactly that — see §4 below.

**Non-negotiable scope boundary:** the bridge is *conceptual*. Validation is simplified sanity checks only, not professional engineering. The disclaimer must stay visible in the UI.

---

## 2. How to run

```bash
conda activate coalitions
streamlit run app.py
```

- Tests: `conda run -n coalitions pytest tests/ -q` → must stay **12/12 green**.
- Mock mode toggle is a sidebar checkbox; backed by `settings.use_mock_llm`. Mock mode runs the entire pipeline offline in seconds via `src/llm/mock.py` (deterministic role-keyed router). Real mode uses OpenAI (`gpt-4o`, `text-embedding-3-small`) via [src/llm/openai_client.py](src/llm/openai_client.py).
- `.env` already configured (Atlas URI, DB `agent_coalitions`, OpenAI key). Do not commit secrets.
- Cluster: MongoDB Atlas M10 in eu-west-2. Database: `agent_coalitions`. Vector index: `skills_embedding_vector` (1536-d cosine on `skills.embedding`).

---

## 3. Architecture in 30 seconds

```
prompt → decomposer → for each subtask:
                        embed(prompt + capability)            ← anchored query
                        Atlas Vector Search on skills          (Mongo role #1)
                        coverage floor 0.40                    (drops off-domain)
                        greedy coalition (≤3 agents)           (induced-subgraph value)
                        set-cover assignment                   (one skill → one agent)
                        blackboard collab, 3 rounds            (Mongo role #2: msg bus)
                        Shapley credit                         (closed form)
                     → synthesiser → spec
                     → validator → checks
                     → visualiser → 3D primitives
                     → reputation update                       (Mongo role #3)
                     → report
```

Read [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) for the single-page methodology with ASCII infographics. Then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component/dataflow/ER schemas. Then [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md) for the maths.

### 3.1 Codebase map

```
app.py                          # Streamlit app, 8 tabs, live progress
src/run.py                      # CLI entry (rare; UI is the demo surface)
src/core/config.py              # settings (env vars, USE_MOCK_LLM flag)
src/db/client.py                # PyMongo client + db handle (singleton)
src/db/writes.py                # insert_with_event() — every write also emits an event row
src/db/matching.py              # search_skills(): wraps the Atlas Vector Search aggregation
src/llm/openai_client.py        # chat() + embed(); retries; falls back to mock on failure
src/llm/mock.py                 # deterministic role-keyed router, used in mock mode
src/llm/prompts.py + prompts/   # Jinja2 templates per role
src/agents/coalitions.py        # COALITION VALUE + SHAPLEY  (the maths heart)
src/pipeline/orchestrator.py    # top-level run loop, persists run doc, calls every stage
src/pipeline/decompose.py       # prompt → subtasks
src/pipeline/execution.py       # subtask → coalition → blackboard → contributions ★
src/pipeline/reputation.py      # apply_run_reputations(): mean_contribution + delta
src/pipeline/visualiser.py      # spec → 3D primitives (boxes + lines)
src/ui/render3d.py              # primitives → Plotly figure
src/ui/bridge_view.py           # legacy 2D side-elevation (still wired in but de-emphasised)
data/skills_seed.json           # 70 skills × 3 capabilities, embeddings cached
data/agents_seed.json           # 20 agents + 1 marshal, owning skills round-robin
tests/                          # 12 tests; all must pass
docs/                           # see §3.2
```

### 3.2 Documentation map

- [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) — single-page methodology with ASCII infographics. **Start here.**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — component/dataflow/ER + mock-vs-real switchboard.
- [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md) — Shapley, induced-subgraph game, glossary, "where each number is used in the UI" mapping table.
- [docs/TEAMS_TAB.md](docs/TEAMS_TAB.md) — line-by-line spec of the Teams tab and the contributions table.
- [docs/MVP_DESIGN.md](docs/MVP_DESIGN.md) — original design + amendments log.
- [docs/PLAN.md](docs/PLAN.md) — gate-by-gate plan.
- [docs/SKILL_SEEDING.md](docs/SKILL_SEEDING.md) — how the 70-skill / 20-agent seed is built.
- [docs/TODO.md](docs/TODO.md) — the backlog (also reproduced in §6 of this doc).

---

## 4. The maths (do not change without reading the primer)

### 4.1 Constants — `src/agents/coalitions.py`

```
ALPHA  = 0.6     # weight of coverage in solo value
BETA   = 0.3     # weight of prior reputation
GAMMA  = 0.1     # weight of log(installs)
LAMBDA = 0.4     # complementarity (edge weight) coefficient
MAX_COALITION = 3
TAU    = 0.05    # marginal-gain threshold to add a 2nd/3rd agent
```

### 4.2 Solo value (per skill)

`aᵢ = v({s}) = α·coverage + β·prior_reputation + γ·log(1+installs)/max_log_installs`

Coverage = cosine(prompt-anchored embedding, skill embedding).

### 4.3 Edge weight (complementarity)

`wᵢⱼ = λ·(1 − cos(eᵢ, eⱼ))` — two skills pointing in different directions in embedding space cover more between them than either alone.

### 4.4 Coalition value (induced-subgraph game, Deng-Papadimitriou 1994)

`v(S) = Σᵢ aᵢ + Σ_{i<j ∈ S} wᵢⱼ`

### 4.5 Shapley value, closed form

`φᵢ = aᵢ + ½·Σⱼ≠ᵢ wᵢⱼ` — exact, O(k²) where k≤3. Implemented in [src/agents/coalitions.py](src/agents/coalitions.py) as `shapley_values(coalition) -> dict[str, float]`. Sums to `v(N)` by the efficiency axiom.

### 4.6 Contribution % (a.k.a. normalised / standardised Shapley value, share of credit)

`contribution % = 100 · φᵢ / Σⱼ φⱼ`.

> ⚠️ **Naming caveat baked into the docs.** `contribution %` is **NOT** the same as a *marginal contribution* `v(S∪{i}) − v(S)`. The Shapley value averages those marginal contributions over all orderings; `contribution %` rescales the Shapley value to the team total. Do not rename the column to "marginal contribution" — that would be technically wrong and the user has been warned about this confusion specifically.

### 4.7 Reputation delta

`delta = base · (0.5 + 0.5·load_factor) · (0.5 + 0.5·quality_factor)`
where `base = +0.04 / +0.02 / −0.04` for pass/warning/fail and `quality_factor = mean of solo values aᵢ` over the skills the agent contributed in the run. See [src/pipeline/reputation.py](src/pipeline/reputation.py).

---

## 5. Domain-alignment fix — the most fragile thing in the codebase

User's recurring complaint: in **real-LLM mode**, off-domain skills (`propulsion-systems`, `embedded-firmware`, `cloud-orchestration`) sometimes ended up on bridge teams. This was fixed in commit `a3b59f0` with two layered changes in [src/pipeline/execution.py](src/pipeline/execution.py):

1. **Prompt anchoring.** `_candidates_for(subtask)` now reads `db.runs.find_one({run_id})['prompt']` and embeds `f"{run_prompt}\n{capability}"` for the cosine match. Atlas Vector Search recall (`search_skills(cap, limit=8)`) still uses the bare capability so the candidate set stays broad — it's the *scoring + floor* that enforces domain alignment.
2. **Coverage floor `0.40`** (raised from 0.30). Real `text-embedding-3-small` produces ~0.4–0.5 cosine between any two engineering strings, so a 0.30 floor was too forgiving.

If you ever see off-topic skills creeping back in, the escalation order is:

1. Raise `COVERAGE_FLOOR` further (0.45 → 0.50) — try this first.
2. Re-rank Atlas hits using the anchored query (currently the *retrieval* uses the bare capability; you can also pass the anchored query into `search_skills`).
3. Reduce `LAMBDA` so complementarity bonuses don't drag off-topic skills onto teams.
4. Increase `ALPHA` so the solo value (which is now anchored) dominates the coalition score.

**Do not** revert the prompt anchoring or lower the floor without testing on a bridge prompt in real-LLM mode end-to-end.

---

## 6. Pending work — TODO

These are deliberately deferred from the 1-day MVP. Live status in [docs/TODO.md](docs/TODO.md).

### 6.1 Hackathon gate status (live)

- [x] G1 conda env
- [x] G2 config + secrets
- [x] G3 Mongo connectivity (13 collections + vector index)
- [x] G4 skills ingested (70 skills, 20+1 agents)
- [x] G5 Atlas Vector Search live
- [x] G6 mock pipeline end-to-end (12/12 tests green)
- [ ] **G7 real-LLM pipeline** — used for the demo video, not the live demo. Needs an end-to-end smoke run with `USE_MOCK_LLM=false` and a screenshot of the bridge tab + teams tab as evidence.
- [x] G8 Streamlit UI — live progress + 8 tabs + 3D bridge viz
- [x] G9 replay
- [x] G10 reputation persists across runs
- [ ] **G11 demo script (≤90 s)** — write the literal words for the pitch. The brief §4 has a draft.

### 6.2 Backlog (post-hackathon)

- [ ] Replace hand-authored `data/skills_seed.json` (~70 entries) with **150 real skills.sh entries**. (See brief Q2.)
- [ ] **Add parity tests for the LLM judge.** *Both* judges already exist in production: the mock judge in [src/llm/mock.py](../src/llm/mock.py) (`_judge`) and the real LLM judge in [src/pipeline/validation.py](../src/pipeline/validation.py) (calls `chat(role="judge")`). What is missing is *automated parity tests* that exercise both and assert their output shape and score ranges agree. This is purely test-coverage work; the runtime path is fine.
- [ ] §11.2 strategy comparison (A: random, B: top-by-reputation, C: our mechanism) — would need gate **G12**.
- [x] **AI hero render via OpenAI image API + "Concept render" tab — gate G13.** Done on branch `langgraph`. Stage module [src/pipeline/concept_render.py](../src/pipeline/concept_render.py) plus an on-demand Streamlit tab. Real mode calls `gpt-image-1`; mock mode (and any API failure) falls back to a deterministic SVG placeholder so the demo never blanks out. Persisted as `artifacts.kind="concept_render"`, replayable like every other artifact. Idempotent per run.
- [ ] Tighten validator: dynamic-load factor, fatigue check stub, deflection limit.
- [x] **Cache LLM responses in a Mongo `llm_cache` collection.** Done on branch `langgraph`. Opt-in via `USE_LLM_CACHE` (default on). Applies to chat + embeddings; cache hits do **not** bump the LLM call counter, preserving the G9 replay invariant. Cache key = sha256 of (kind, model, role+prompt).
- [ ] Runtime assertion that no `chat()` call goes out when `settings.use_mock_llm=True`.
- [x] **Implement LangGraph in another branch.** Done on branch `langgraph` (commits `3ab7ff8` + `208111d`). Parallel implementation in [src/pipeline/orchestrator_lg.py](../src/pipeline/orchestrator_lg.py) behind a runtime flag; sidebar toggle, status badge, and a *🕸️ Workflow* tab that renders the compiled graph as a Mermaid diagram. 14/14 tests pass against both backends. See [docs/LANGGRAPH.md](LANGGRAPH.md). The migration plan in §12 below is preserved as a record of how the port was scoped.
- [ ] Hard-FAIL validation category (currently warnings only).
- [ ] Investigate identical-skills duplication across teams (by design today; flag if it confuses judges).

---

## 7. Things that look broken but aren't

These have all tripped the user (and prior agents) at least once. Don't "fix" them.

1. **`prior_reputation` and `weekly_installs` look static across teams** in the Teams tab. They are. They live on the *skill*, not on the assignment.
2. **The same skill can appear in two different teams.** By design — two subtasks may share required capabilities. Caption explains this.
3. **A 1-agent team has `contribution % = 100 %`.** Trivially true: Shapley of a lone player = `v({s})`, no orderings to average over.
4. **There is no "team total" Shapley badge.** Could be added; deliberately omitted for now.
5. **Bridge 3D render compresses scale.** Intentional. `src/ui/render3d.py` uses `aspectmode="manual"` with `aspectratio = (extent / max_extent) ** 0.5` — see §8 below.
6. **Score column was deleted from the Teams tab.** Honest naming: per-skill solo value `aᵢ` is not a meaningful per-agent metric for a multi-skill team (it ignores complementarities). Still computed and persisted as `assignments.contribution_scores[*].score` for the reputation step. Don't put it back in the UI without re-reading [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md) §9b.
7. **Agent labels are just `#017`** with no skill keyword suffix. The suffix used to leak unrelated owned skills into the label (a bridge agent might display "propulsion" because the agent happened to also own that skill). Removed deliberately.
8. **Live-progress widgets clear on `pipeline_end`.** Otherwise stale snapshot lingered.
9. **No "Replay current run" button.** It was flaky; removed.
10. **f-string with `\u2014`.** There is a hoisted `EM_DASH = "\u2014"` constant in [app.py](app.py) because Python 3.11 forbids backslashes inside f-string `{...}` expressions. Don't inline it.

---

## 8. The 3D rendering — what's there and what's next

[src/ui/render3d.py](src/ui/render3d.py) is **domain-agnostic**: it draws whatever primitives `src.pipeline.visualiser` produces (`box` = axis-aligned cuboid, `line` = polyline). The visualiser is the only domain-aware piece.

Key recent fixes:

- `aspectmode="manual"` with **`aspectratio = (extent / max_extent) ** 0.5`** — squashes the dominant axis so long-thin structures (bridges) don't crush vertical features to invisibility. Per-axis floors of 0.25 / 0.40 stop degenerate cases collapsing entirely.
- Figure height bumped to 760 px; camera `eye=(1.35, −1.55, 0.85)`.
- Default girder bridges now get **abutments at each bank, parapet edge beams along the deck, and shore strips** so they read as bridges instead of black slabs on water.

The aspect-ratio formula generalises: rollercoasters, towers, planes all render with sensible proportions because the formula re-balances based on relative extents, not absolute scale.

Outstanding rendering work:

- AI hero render (OpenAI image API) — done on `langgraph` branch (see §6.2).
- Real-mode LLM Visualiser path is implemented (`src/pipeline/visualiser.py` calls `chat(role="visualiser")`) but falls back to deterministic builders on parse/validation error. Expand the schema-shaped prompt for tower/dam/coaster if you want richer LLM-generated geometry.

---

## 9. UI glossary (Teams tab columns)

- `agent` — short label `#NNN` or `Marshal`.
- `shapley` — exact Shapley value `φᵢ = aᵢ + ½·Σ wᵢⱼ`, **rounded to 2 decimals**. Sums to `v(N)`.
- `contribution %` — `100·φᵢ/Σⱼ φⱼ`. A.k.a. normalised Shapley / share of credit. **Not** marginal contribution.
- `skills_contributed` — set-cover assignment of skills to this agent in this team.

Reputation tab: `agent`, `subtasks_participated`, `mean_contribution_score`. The columns `delta` and `reason` were removed from the UI but are still persisted on `reputation_updates` for audit.

---

## 10. Working norms (please respect)

The user has given clear, repeated instructions across this build:

- **Be brief.** No emojis. No unsolicited expansion.
- **Only do what is asked.** No "improvements" thrown in. No new files unless asked.
- **Tests must stay green** after every change. `conda run -n coalitions pytest tests/ -q` → 12/12.
- **Real LLM mode is the demo target.** Mock mode is for offline reproducibility, not the source of truth. If a fix only works in mock mode, it doesn't work.
- **Honest naming.** The user pushed back on misleading labels several times (`score` masquerading as "credit", agent labels showing unrelated skills). When in doubt, pick the technically correct term and explain it in the footnote.
- **Methodology lives in `docs/MATCHING_PIPELINE.md`.** That is "the bread and butter." Update it when you change the pipeline. Same for [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md) §9c when you change a UI column.
- **Do not push to remote, do not force-push, do not amend published commits** without explicit user confirmation.

---

## 11. Quickstart for the next agent

1. Read [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) (5 minutes).
2. Skim [docs/GAME_THEORY_PRIMER.md](docs/GAME_THEORY_PRIMER.md) §9, §9b, §9c (5 minutes).
3. `conda run -n coalitions pytest tests/ -q` — confirm 12/12 green.
4. `streamlit run app.py`, run the default bridge prompt with mock mode ON, then OFF. Confirm:
   - All 8 tabs populate.
   - Teams tab contributions table has `agent | shapley | contribution % | skills_contributed`.
   - 3D bridge looks like a bridge (deck, two abutments, intermediate piers, parapets, banks).
   - No `propulsion-systems`, `embedded-firmware`, `cloud-*` in any team.
5. Read this doc's §6 TODO list and pick one.
6. Commit with a descriptive message. Don't push without asking.

Good luck.

---

## 12. LangGraph migration — concrete plan for the next agent

The brief asks for LangGraph. We chose a plain function pipeline for the 1-day MVP (see the docstring at the top of [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py): *"plain function pipeline — escape hatch per Amendment 3.14"*). The port should be done **on a branch**, never on master, so the working demo keeps working.

### 12.1 Where the current pipeline lives

The whole sequence is in **`run_pipeline(prompt: str)`** inside [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py). It calls 9 stage functions, each of which already encapsulates its own MongoDB writes:

| Stage | Function | Module | Writes (MongoDB collections) |
| --- | --- | --- | --- |
| 1. ensure_run | `_ensure_run(prompt)` | `orchestrator.py` (private) | `runs`, `events` |
| 2. decompose | `decompose(run_id, prompt)` | [src/pipeline/decomposer.py](src/pipeline/decomposer.py) | `subtasks`, `events` |
| 2.5. validator spec | `derive_validation_spec(run_id, prompt)` | [src/pipeline/validator_spec.py](src/pipeline/validator_spec.py) | `runs.validation_spec`, `events` |
| 3. execute (loop over subtasks) | `execute_subtask(run_id, st, upstream, criteria)` | [src/pipeline/execution.py](src/pipeline/execution.py) | `assignments`, `coalition_messages`, `subtask_outputs`, `events` |
| 4. synthesise | `synthesise(run_id, prompt)` | [src/pipeline/synthesis.py](src/pipeline/synthesis.py) | `design_specs`, `events` |
| 5. validate | `validate(run_id, spec)` | [src/pipeline/validation.py](src/pipeline/validation.py) | `validation_results`, `events` |
| 6. estimate cost | `estimate(run_id, spec)` | [src/pipeline/surveyor.py](src/pipeline/surveyor.py) | `cost_estimates`, `events` |
| 7. visualise | `build_geometry(run_id, spec)` | [src/pipeline/visualiser.py](src/pipeline/visualiser.py) | `artifacts` (kind=geometry_json), `events` |
| 8. report | `build_report(run_id, prompt, spec, validation, cost)` | [src/pipeline/reporter.py](src/pipeline/reporter.py) | `artifacts` (kind=final_report_md), `runs.final_report_md`, `events` |
| 9. reputation | `apply_run_reputations(run_id, status)` | [src/pipeline/reputation.py](src/pipeline/reputation.py) | `reputation_updates`, `agents.reputation`, `events` |

These stage functions are **already pure-ish nodes**: each takes `run_id + a few primitive args + the upstream artifacts it needs`, does its work, and returns the data the next stage needs. That is exactly the shape LangGraph expects.

### 12.2 The mapping (what becomes what)

LangGraph nodes are functions `(state) -> partial_state`. So:

```python
# new file: src/pipeline/orchestrator_lg.py     (parallel to the existing one)

from typing import TypedDict, Any
from langgraph.graph import StateGraph, END

class GraphState(TypedDict, total=False):
    run_id: str
    prompt: str
    subtasks: list[dict]            # ordered (topological) — set by decompose_node
    criteria: list[dict]            # set by validator_spec_node
    spec: dict                      # set by synthesise_node
    validation: dict
    cost: dict
    report_md: str
    n_reputation_updates: int
    error: str | None

def ensure_run_node(s: GraphState) -> dict:
    run_id = _ensure_run(s["prompt"])           # reuse existing private helper
    return {"run_id": run_id}

def decompose_node(s: GraphState) -> dict:
    subs = decompose(s["run_id"], s["prompt"])
    return {"subtasks": _topo_order(subs)}

def validator_spec_node(s: GraphState) -> dict:
    spec = derive_validation_spec(s["run_id"], s["prompt"])
    return {"criteria": spec.get("criteria", [])}

def execute_node(s: GraphState) -> dict:
    # Sequential loop — keep semantics identical to today.
    for st in s["subtasks"]:
        st_doc = {**st, "run_id": s["run_id"]}
        upstream = _upstream_outputs(s["run_id"], st_doc)
        execute_subtask(s["run_id"], st_doc, upstream, criteria=s["criteria"])
    return {}

def synthesise_node(s: GraphState) -> dict:
    return {"spec": synthesise(s["run_id"], s["prompt"])}

def validate_node(s: GraphState) -> dict:
    return {"validation": validate(s["run_id"], s["spec"])}

def cost_node(s: GraphState) -> dict:
    return {"cost": estimate(s["run_id"], s["spec"])}

def visualise_node(s: GraphState) -> dict:
    build_geometry(s["run_id"], s["spec"])
    return {}

def report_node(s: GraphState) -> dict:
    md = build_report(s["run_id"], s["prompt"], s["spec"], s["validation"], s["cost"])
    return {"report_md": md}

def reputation_node(s: GraphState) -> dict:
    n = apply_run_reputations(s["run_id"], s["validation"]["overall_status"])
    return {"n_reputation_updates": n}

def finalise_node(s: GraphState) -> dict:
    # The block at the bottom of run_pipeline(): runs.update_one + run_completed event.
    ...

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("ensure_run", ensure_run_node)
    g.add_node("decompose", decompose_node)
    g.add_node("validator_spec", validator_spec_node)
    g.add_node("execute", execute_node)
    g.add_node("synthesise", synthesise_node)
    g.add_node("validate", validate_node)
    g.add_node("cost", cost_node)
    g.add_node("visualise", visualise_node)
    g.add_node("report", report_node)
    g.add_node("reputation", reputation_node)
    g.add_node("finalise", finalise_node)
    g.set_entry_point("ensure_run")
    g.add_edge("ensure_run", "decompose")
    g.add_edge("decompose", "validator_spec")
    g.add_edge("validator_spec", "execute")
    g.add_edge("execute", "synthesise")
    g.add_edge("synthesise", "validate")
    g.add_edge("validate", "cost")
    g.add_edge("cost", "visualise")
    g.add_edge("visualise", "report")
    g.add_edge("report", "reputation")
    g.add_edge("reputation", "finalise")
    g.add_edge("finalise", END)
    return g.compile()
```

### 12.3 Concrete checklist

1. `git checkout -b feat/langgraph-orchestrator`.
2. Add a new file [src/pipeline/orchestrator_lg.py](src/pipeline/orchestrator_lg.py). **Do not delete or modify [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py).** Keep both side-by-side.
3. Reuse the private helpers `_ensure_run`, `_topo_order`, `_upstream_outputs`, `_now` — either move them out of `orchestrator.py` into a small `src/pipeline/_run_utils.py` (preferred), or import them directly. If you move them, update both files.
4. Reuse every stage function exactly as-is. **Do not** re-implement Mongo writes inside the nodes. Each node is a thin wrapper; the side-effects (DB writes, `events` rows) stay where they already live.
5. Preserve the **`emit(...)` progress hooks** from `src.core.progress` — wrap each node call so the Streamlit live-progress UI keeps working. Pattern: emit `stage_start` / `stage_end` either in the node body or via a small decorator. Without these the live-progress widgets in [app.py](app.py) will go silent.
6. Add a feature flag in [src/core/config.py](src/core/config.py): `use_langgraph: bool = False`, env var `USE_LANGGRAPH`. In [app.py](app.py), branch on `settings.use_langgraph` to import either `run_pipeline` from `orchestrator.py` or a `run_pipeline_lg(prompt)` shim that drives the compiled graph and returns the same summary dict.
7. The `run_pipeline_lg` shim must return the same dict shape as today's `run_pipeline` (`{run_id, subtasks, validation, cost_total, reputation_updates, report_md_chars}`) so [app.py](app.py) does not need conditional rendering downstream.
8. Mirror the **replay path** (`replay(run_id)` in `orchestrator.py` lines ~200+). Replay must remain a no-LLM path — read existing rows from Mongo and never enter the graph. Keep replay outside LangGraph; the graph is only for live runs.
9. Tests: copy [tests/test_orchestrator.py](tests/test_orchestrator.py) to `tests/test_orchestrator_lg.py` and run the same assertions against the LangGraph path. Both must pass. **Goal: 12/12 → 18/18 (or whatever the new total is) green.**
10. Do **not** introduce LangGraph's checkpointer (SqliteSaver / MemorySaver) in the first cut. Our state is already persisted in MongoDB; adding a second store is a foot-gun. If the user wants pause/resume later, that becomes a separate ticket.
11. Do **not** add LangGraph subgraphs for the `execute` loop on the first cut. Keep it a single sequential node that loops `execute_subtask` like the current orchestrator does. Parallelising subtasks is a separate ticket and breaks the dependency-aware `_topo_order` semantics if done naively.
12. Update [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) with a new "Orchestration backend" subsection showing both options. Update [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) only if the *user-visible* flow changes (it shouldn't).
13. Open a PR titled `feat: LangGraph orchestrator (parallel implementation, opt-in flag)`. Do **not** delete the function pipeline in this PR. The user has been explicit about not breaking the working demo.

### 12.4 What NOT to do

- Do not rewrite the stage functions to be LangGraph-aware. They are domain-clean today; keep them that way.
- Do not move MongoDB writes out of the stage functions into the nodes.
- Do not wire LLM calls into LangGraph's tool-calling abstractions. Our LLM client (`src/llm/openai_client.py`) is already a clean seam with mock-mode fallback. LangGraph is the *workflow engine*, not the LLM router.
- Do not add LangChain `Runnable` chains around the nodes "for consistency". They add a 100ms-per-step overhead and obscure the call graph.
- Do not touch [src/agents/coalitions.py](src/agents/coalitions.py) (the maths) or [src/pipeline/execution.py](src/pipeline/execution.py) (the matching loop) at all. They are orthogonal to orchestration.

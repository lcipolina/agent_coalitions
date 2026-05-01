# Capability-Search-Based Delegation System for Multi-Agent Collaboration — MVP Design

> **Hackathon:** MongoDB London — Multi-Agent Collaboration track
> **Source:** https://cerebralvalley.ai/e/mongo-db-london-hackathon/details
> **Build window:** 1 day
> **Audience:** Hackathon judges + technical reviewers
> **Status:** Methodology locked. Amendments dated 2026-05-01 applied (see block below). This document is the contract for the coding agent.
>
> **Note on terminology.** Earlier drafts of this brief called the system a "market". On reflection that word overstates what we build (no prices, no private information, no incentive compatibility). The accurate name is **capability-search-based delegation system**, with the closest legitimate academic analogy being a **one-sided matching mechanism**. The word *market* is **no longer used** anywhere in current usage — UI, code, DB, narration. Appendix A retains the historical discussion of why we don't use it.

---

## Amendments 2026-05-01

Lead-confirmed amendments resolving every ambiguity flagged in `PLAN.md §3`. Where this block conflicts with the body of the document, **this block wins**.

1. **Naming (Q21).** The word "market" is banned in current usage. DB name `agent_market` → **`agent_coalitions`**. Conda env `agent-market` → **`coalitions`**. Project / app title "Agent Market" → **"Agent Coalitions"**. Streamlit tab #2 "Agent Market" → **"Assignments"** (tab #3 "Coalitions" unchanged). Run button "Run Agent Market" → **"Run Coalitions"**. §10 narration drops the "agent market for short" phrasing. Appendix A retained as historical discussion.
2. **Summary token cap (Q1).** Standardised on **≤ 200 tokens** for `subtask_outputs.summary` everywhere. Truncation via `tiktoken`.
3. **Algorithm definitions filled in (§4.2; Q3, Q4, Q5).** `coverage(s, q) = clip(cosine(emb(s), emb(q)), 0, 1)`. `prior_reputation(s)` = min-max normalisation across the catalog of `0.5·log(1+installs) + 0.5·log(1+stars)`. The γ term reads `log(1+installs(s)) / log(1+max_installs_in_catalog)`, ∈ [0,1].
4. **Default 7-subtask DAG (§4.1; Q6).** Used as decomposer fallback and by mock decomposer: T1 Site & geometry; T2 Load profile; T3 Material selection (deps T1,T2); T4 Structural system (deps T1,T2,T3); T5 Aesthetic & elevation guidance (deps T1,T4); T6 Validation prep (deps T3,T4); T7 Final synthesis brief (deps all).
5. **Marshal (§13; Q7).** Single shared synthetic marshal `agent_id = "agent_synthetic_marshal"` for v1.
6. **Validator checks (§4.6 / §3.9; Q8).** Minimum five: `span_to_depth_ratio`, `support_count_consistency`, `live_load_arithmetic`, `material_span_plausibility`, `lane_geometry`. Specific thresholds in `PLAN.md §3.6`.
7. **Cost model (Q9).** Hand-picked unit prices in `cost_model.json`. Currency tag `EUR` retained per spec; values reasonable US-style (steel $3,500/t, weathering steel $4,000/t, concrete $180/m³, deck slab $350/m², piers $150,000 each, abutments $220,000 each, finishing premium 10%, contingency 15%).
8. **Schema additions (Q10, Q11, Q24).** `validation_results` gains `judge_scores: [{subtask_id, clarity, completeness, consistency, rationale}]`. `runs` gains `config: {seed, git_sha, use_mock_llm}` (top-level `runs.use_mock_llm` collapsed into config). `runs.summary_metrics.estimated_cost_eur` is a denormalised copy of `cost_estimates.total`.
9. **Blackboard simplification (§4.5; Q23).** Coalition agents post in **parallel** in round 1, seeing only the marshal kickoff and upstream `subtask_outputs.summary`. Agents do not see each other's contributions in round 1. Marshal then reconciles in round 2; one optional revision round (round 3) follows if conflict flagged.
10. **Replay verification (Q13).** `src/llm/openai_client.py` exposes a process-local call counter; replay path resets it then asserts `== 0` at end. Replay events are tagged `kind: "replay"`.
11. **Vector index creation (Q14).** `src/db/indexes.py` calls `database.create_search_index(...)`. Soft-fail with explicit error if cluster lacks Atlas Search.
12. **Disclaimer string (Q22).** Canonical text used verbatim everywhere: *"Conceptual design produced by an experimental multi-agent system. Not certified engineering. Not for construction."*
13. **Synthetic agent population (§3.2; Q17).** 20 agents: 14 with 2 skills, 4 with 3 skills, 2 with 4 skills.
14. **Orchestrator (Q20).** LangGraph, with pre-approved escape hatch to a plain function pipeline if it blocks gate G6 by more than ~30 minutes.
15. **`skills_seed.json` (Q2).** ~30–50 hand-authored entries for v1. Swap to 150 real skills.sh entries is tracked in `TODO.md`.
16. **Mock LLM judge (Q16).** Mock mode returns templated mid scores so the radar chart populates. Switch to real judge in mock-mode tracked in `TODO.md`.
17. **`llm_cache` collection (Q12).** Skipped for MVP. Replay reads `subtask_outputs` / `coalition_messages` directly.
18. **Repo layout (Q24/§8).** Workspace root *is* the project root; no nested `agent_market/` directory. The DB name `agent_coalitions` provides the namespace separation.
19. **Test scope (§8 / §9.6; Q18).** The four files in §8 are authoritative.
20. **Stretch (Q15, Q19).** §11.2 strategy comparison and §5.3 AI hero render are stretch gates G12 / G13 — not part of definition-of-done.

See `PLAN.md` for the executable plan.

---

## Hackathon Premise (Track 2 — Multi-Agent Collaboration)

> Develop a multi-agent system in which specialized agents explore, assign tasks, and communicate with one another, using MongoDB to organize and oversee contexts. How do agents convey their skills, identify suitable peers for a sub-task, share context effectively within token limits, and perform intricate tasks resulting from successful collaborations?

This document answers each of the four questions in the prompt directly:

1. **How do agents convey their skills?** A real public skills catalog (skills.sh) is ingested into MongoDB; each agent's skills are embedded with `text-embedding-3-small` and stored alongside a `prior_reputation` scalar derived from installs/stars and updated across runs (§3.1, §3.2).
2. **How do they identify suitable peers for a sub-task?** Atlas `$vectorSearch` retrieves ~10 candidate skills per subtask, then a pairwise-complementarity coalition formation step (rank-1 Shapley over an induced subgraph game) picks a coalition of 1–3 agents (§4.2, §4.3).
3. **How do they share context effectively within token limits?** Two complementary channels, both backed by MongoDB: an append-only blackboard for in-coalition messages with a single revision pass, and a strict ≤200-token `subtask_outputs.summary` that is the only thing crossing subtask boundaries (§3.6, §4.5, §9.1 constraint #8).
4. **How do they perform intricate tasks resulting from successful collaborations?** Subtasks execute in topological order over the DAG; a synthesizer + validator + quantity surveyor + visual designer assemble the per-subtask summaries into a government-bid-style proposal, and reputation is updated for the next run (§4.5–§4.7, §10).

MongoDB is the single substrate for all five roles this requires: skills inventory, assignment ledger, blackboard message bus, cross-subtask context store, and persistent reputation memory.

---

## TL;DR

A complex brief (*"design a 2 km bridge for 50 cars/h"*) needs many skills no single agent has. An orchestrator LLM decomposes it into a subtask DAG with required capabilities. For each subtask, MongoDB Atlas Vector Search narrows a real skills catalog (skills.sh) to ~10 candidates; a pairwise-complementarity score (rank-1 Shapley over an induced subgraph game) picks a coalition of 1–3 agents. The coalition collaborates on a MongoDB-backed append-only blackboard coordinated by an LLM marshal, and produces a ≤200-token summary — the only thing that crosses subtask boundaries. Downstream subtasks read upstream summaries from MongoDB the same way. A synthesizer + validator + quantity surveyor + visual designer turn it all into a government-bid-style proposal. MongoDB plays five roles: skills inventory, assignment ledger, blackboard message bus, cross-subtask context store, persistent reputation. One Python process, one Atlas cluster, one OpenAI key. Not a market in the economic sense (Appendix A); not certified engineering.

---

## Abstract

Real-world tasks routinely exceed the capability of any single LLM agent: they require structural reasoning, numerical analysis, materials knowledge, costing, aesthetic judgement, and synthesis, all in one coherent answer. Hand-wired multi-agent pipelines solve this only for tasks the engineer anticipated. Free-for-all chat rooms scale poorly and explode token budgets. Server-to-server agent protocols (MCP, A2A) are production infrastructure incompatible with a one-day build.

We propose a **centralised, capability-search-based delegation system** that handles the general case in a single Python process. The pipeline has five stages, each addressing a distinct challenge:

1. **Decomposition.** An orchestrator LLM reads the user brief and emits a DAG of subtasks, each annotated with free-text required capabilities. This is the planning stage. Output is stored in MongoDB.

2. **Capability search.** Skills are first-class objects ingested from a real public catalog (skills.sh) into MongoDB. For each required capability we run **MongoDB Atlas Vector Search** to retrieve the top-K semantically nearest skills, reducing a catalog of thousands to a per-subtask shortlist of ~10. This is the dimensionality-reduction step.

3. **Coalition formation.** Among the shortlist, we model the value of a candidate team as a **node-weighted induced subgraph game** (Deng & Papadimitriou, 1994): solo terms from skill relevance and prior reputation, edge weights from embedding-derived complementarity. The Shapley value of this game has a closed form — each skill earns its solo value plus half the sum of its complementarity edges. We select a coalition of 1–3 by greedy marginal contribution, then map skills to actual agents (skill bundles) via greedy set-cover. The orchestrator computes a deterministic **contribution score** for each candidate; there is no LLM bidding theatre.

4. **Coalition execution.** Each coalition collaborates on a per-subtask **append-only blackboard** stored as a MongoDB collection. An LLM **marshal** posts a kickoff brief, each agent posts its contribution while reading the log so far, and the marshal reconciles (with at most one revision round) into a single token-bounded summary (≤ 200 tokens). Only the summary crosses the subtask boundary. The same mechanism handles intra-coalition and inter-subtask context sharing.

5. **Synthesis and delivery.** A synthesizer, validator, quantity surveyor, and visual designer run in parallel on the assembled subtask outputs, and a final-report agent produces a markdown government-bid proposal containing two visualizations (Plotly engineering schematic + a hand-built stylised SVG architectural elevation), a deterministic validation card, and a costed budget. Agent reputations are updated and persisted.

The result is a system that addresses every clause of the hackathon prompt — *agents convey their skills (catalog ingestion), identify suitable peers (vector search + complementarity), share context within token limits (marshal-consolidated summaries), and perform intricate tasks resulting from successful collaborations (synthesis pipeline)* — using a single Python process with no servers and no agent-to-agent network protocol. MongoDB Atlas is not a database in the sidecar sense; it plays five distinct architectural roles — skills inventory, assignment ledger, blackboard message bus, cross-subtask context store, and persistent reputation memory — and removing it removes five capabilities. The demo use case is conceptual infrastructure design; the end artefact is a government-bid-style proposal document. We deliberately do not claim to be a market in the economic sense (Appendix A) or a certified engineering tool (§ 1.4).

---

## 1. Introduction

### 1.1 The problem

The hackathon track asks: *"How do agents convey their skills, identify suitable peers for a sub-task, share context effectively within token limits, and perform intricate tasks resulting from successful collaborations?"*

Every published multi-agent demo we have seen handles this with one of three patterns:
- **Hand-wired pipelines** — works, but no delegation actually happens.
- **Free-for-all chat rooms** — does not scale; tokens explode; no provenance.
- **Server-to-server agent protocols (MCP, A2A)** — production-grade infrastructure incompatible with a one-day build.

None of them addresses the *combinatorial* nature of delegation when the agent population is large and capabilities overlap.

### 1.2 Our claim

Delegation in a large agent population can be reframed as **centralised capability search plus cooperative-game-theoretic coalition selection**, where MongoDB Atlas plays the role of the shared registry, ledger, and message bus. Specifically:

- Agents are *not* daemons. They are profiles in a Mongo collection. The orchestrator instantiates them by sending an LLM call against the profile.
- Skills are first-class objects sourced from a real public catalog.
- Selection is a **two-stage filter**: semantic search reduces the candidate set; pairwise complementarity selects the coalition.
- Collaboration inside a coalition uses an **append-only log** that is literally a Mongo collection; the protocol is *write-and-read*, not *send-and-receive*.

We deliberately do **not** claim this is a market in the economic sense. There are no prices, no private information, no strategic agents, and no incentive-compatibility guarantees. The mechanism is a *centralised matching* with a structured scoring rule, closest in spirit to one-sided matching mechanisms in the Roth–Sönmez–Ünver tradition. See **Appendix A** for the precise framing.

### 1.3 What is novel here

| Aspect | Conventional approach | This MVP |
|---|---|---|
| Agent discovery | Hardcoded list | Vector search over real skills catalog |
| Coalition selection | Brute force or hand-wiring | Pairwise complementarity (rank-1 Shapley) |
| Inter-agent comms | RPC, queue, or implicit | Mongo append-only blackboard |
| Context sharing | Pass full outputs | Marshal-consolidated summaries only |
| Audit trail | Logs scattered in stdout | Single Mongo source of truth, judge-visible |
| Reputation | None | Persistent across runs |

### 1.4 Non-goals (explicit)

We do **not** build:
- distributed agent runtimes, MCP servers, or A2A protocols
- finite element analysis, real engineering certification, code-compliant design
- 3D rendering, CAD export, AR/VR
- exact Shapley computation
- authentication, multi-tenant deployment
- production-grade cost accounting

The disclaimer *"this is conceptual; not certified engineering"* must appear in the UI and the final report.

---

## 2. System Overview

### 2.1 One-paragraph mental model

A user submits a prompt. An LLM **decomposer** turns it into a DAG of subtasks, each annotated with required capabilities. For every subtask, the orchestrator (a) queries `skills` via Atlas Vector Search, (b) runs pairwise-complementarity coalition selection to pick 1–3 skills, (c) maps skills to agents via greedy set-cover, (d) opens a blackboard log in Mongo, (e) lets an LLM **marshal** kick off, (f) lets each agent post a contribution, (g) lets the marshal reconcile and write a final summary. Subtasks run in topological order; downstream agents read upstream summaries from Mongo. After all subtasks finish, a **synthesizer** produces a unified design spec, three end-of-pipeline agents (validator, quantity surveyor, visual designer) run in parallel, and a **final report agent** writes a markdown government-bid proposal. Reputation is updated and persisted. The demo is run twice to prove persistence.

### 2.2 ASCII architecture

```
                 ┌────────────────────────────────────────────┐
                 │ Streamlit UI                                │
                 │ tabs: Overview · Assignments · Coalitions · │
                 │       Design · Validation · Budget ·        │
                 │       MongoDB Records · Final Report        │
                 └──────────┬──────────────────────┬───────────┘
                            │                      │
                  user prompt│                  read everything
                            ▼                      │
        ┌──────────────────────────────────────────┴──────────┐
        │ Orchestrator (single Python process, LangGraph)     │
        │                                                     │
        │  decompose → [ for each subtask in topo order ]:    │
        │     1. vector-search skills                         │
        │     2. pairwise-complementarity coalition           │
        │     3. set-cover skills → agents                    │
        │     4. marshal opens blackboard                     │
        │     5. agents post contributions                    │
        │     6. marshal reconciles + final summary           │
        │  synthesize → validate ‖ cost ‖ visualize → report  │
        │  update reputation                                  │
        └────────────┬─────────────────────────────────┬──────┘
                     │   read/write everything         │
                     ▼                                 ▼
        ┌────────────────────────────┐    ┌────────────────────────┐
        │ MongoDB Atlas              │    │ External APIs          │
        │ - skills (vector index)    │    │ - OpenAI (LLM)         │
        │ - agents                   │    │ - OpenAI (embeddings)  │
        │ - runs                     │    │ - OpenAI (image gen,   │
        │ - subtasks                 │    │   optional WOW render) │
        │ - assignments              │    └────────────────────────┘
        │ - coalition_messages       │
        │ - subtask_outputs          │
        │ - design_specs             │
        │ - validation_results       │
        │ - cost_estimates           │
        │ - artifacts                │
        │ - events                   │
        │ - reputation_updates       │
        └────────────────────────────┘
```

### 2.3 Why MongoDB at every layer

| Mongo feature used | Where | Genuine reason |
|---|---|---|
| `$vectorSearch` over `skills.embedding` + `$match` on installs/stars | Stage 1 of every subtask | Co-located semantic + structured filter; no other DB does both |
| Append-only inserts to `coalition_messages` indexed by `(run_id, subtask_id, ts)` | Coalition collaboration | Concurrent-safe shared log, queryable per-coalition |
| `subtask_outputs.summary` reads scoped by `run_id` and `subtask_id` | Cross-subtask context | The token-bounded message bus |
| Persistent updates to `agents.reputation` | After every run | Required for second-run-changes-selection demo |
| `events` stream rendered in UI | Throughout | Single audit trail visible in "MongoDB Records" tab |

Five distinct uses, all genuine. None reduces to a Python dict without losing a real capability (persistence, concurrent-safe writes, structured + vector co-query, judge-visible provenance).

If a reviewer challenges *"why Mongo and not just dicts?"* the answer is: persistence (reputation), concurrent-safe writes (blackboard), structured + vector co-query (skill search), and judge-visible provenance (Records tab). Removing Mongo means removing five capabilities, not just one.

---

## 3. Data Model (System-Design Schema)

All collections live in the database `agent_coalitions`. Every document carries a `run_id` (ObjectId, UUID, or hash) where applicable. Timestamps are ISO 8601 UTC.

### 3.1 `skills`

Source: ingested from skills.sh (manual JSON dump scrape if no API; cap at ~150 skills filtered to plausibly relevant categories — engineering, design, analysis, writing, math).

```json
{
  "_id": "<auto>",
  "skill_id": "structural-load-estimation",
  "name": "Structural Load Estimation",
  "description": "Estimate dead, live, and dynamic loads on civil structures...",
  "category": "engineering",
  "tags": ["civil", "loads", "kN", "HL-93"],
  "weekly_installs": 12500,
  "github_stars": 88,
  "repo_url": "https://github.com/example/skill",
  "embedding": [/* 1536-dim float vector from text-embedding-3-small */],
  "prior_reputation": 0.71,        // derived from log-installs and log-stars, normalised 0-1
  "created_at": "2026-05-01T08:00:00Z"
}
```

Index: vector index on `embedding` (cosine), regular indexes on `category`, `weekly_installs`.

### 3.2 `agents`

~20 agents synthesised at seed time by sampling 2–4 skills per agent from `skills` (skewed so that a few agents are polyvalent, most are specialists).

```json
{
  "_id": "<auto>",
  "agent_id": "agent_007",
  "name": "Stella Truss",
  "skill_ids": ["structural-load-estimation", "numerical-validation"],
  "polyvalence": 2,                // = len(skill_ids)
  "base_cost": 1.0,
  "base_latency_s": 12,
  "reputation": 0.62,              // initialised from mean of skill prior_reputation; updated after each run
  "runs_participated": 4,
  "runs_succeeded": 3,
  "created_at": "2026-05-01T08:00:00Z",
  "updated_at": "2026-05-01T18:42:11Z"
}
```

Index: `skill_ids` multikey, `reputation`.

### 3.3 `runs`

```json
{
  "_id": "<auto>",
  "run_id": "run_2026_05_01_001",
  "prompt": "Design a 2km bridge for 50 cars/h with trucks, modern aesthetic.",
  "status": "running|completed|failed",
  "use_mock_llm": false,
  "started_at": "...", "completed_at": "...",
  "final_report_md": "...",        // populated at end
  "design_spec_id": "<ref>",
  "summary_metrics": {
     "n_subtasks": 7, "n_assignments": 9, "n_messages": 42,
     "validation_status": "conceptual_pass_with_warnings",
     "estimated_cost_eur": 38400000
  }
}
```

### 3.4 `subtasks`

Created by the decomposer.

```json
{
  "_id": "<auto>",
  "run_id": "...",
  "subtask_id": "T3",
  "title": "Material selection",
  "description": "Choose primary structural material balancing cost, durability, aesthetic.",
  "required_capabilities": ["materials science", "cost analysis", "constructability"],
  "depends_on": ["T1", "T2"],
  "status": "pending|in_progress|complete|failed",
  "topo_index": 2,
  "created_at": "..."
}
```

### 3.5 `assignments`

One per coalition (per subtask). The "contribution score" replaces the old "bid".

```json
{
  "_id": "<auto>",
  "run_id": "...",
  "subtask_id": "T3",
  "coalition_skill_ids": ["materials-science", "cost-analysis"],
  "coalition_agent_ids": ["agent_004", "agent_011"],
  "marshal_agent_id": "agent_synthetic_marshal",   // a special "marshal" role agent
  "contribution_scores": [
    {"agent_id": "agent_004", "score": 0.71, "skills_contributed": ["materials-science"]},
    {"agent_id": "agent_011", "score": 0.66, "skills_contributed": ["cost-analysis"]}
  ],
  "selection_rationale": "Materials-science covers primary requirement; cost-analysis adds complementary coverage with low embedding overlap (cosine 0.31).",
  "created_at": "..."
}
```

### 3.6 `coalition_messages` (the blackboard)

The mental model is **`coalitionN.log`**. Each row is one log line.

```json
{
  "_id": "<auto>",
  "run_id": "...",
  "subtask_id": "T3",
  "ts": "2026-05-01T10:03:14.221Z",
  "sender": "agent_004",            // or "marshal"
  "role": "agent" | "marshal",
  "round": 1,                        // 0=kickoff, 1=contributions, 2=reconcile, 3=revision
  "text": "I propose steel for the truss because ...",
  "meta": {                         // optional, agent may post structured side-channel
    "type": "question_for_marshal" | "structured_output" | null,
    "payload": {}
  }
}
```

Indexes: `(run_id, subtask_id, ts)`.

### 3.7 `subtask_outputs`

The marshal-consolidated, token-bounded summary that *crosses subtask boundaries*. Strict contract: ≤ 200 tokens (per Amendments 2026-05-01).

```json
{
  "_id": "<auto>",
  "run_id": "...",
  "subtask_id": "T3",
  "summary": "Recommend weathering steel for primary truss; concrete deck. Cost premium 8% over plain steel, justified by 50yr maintenance reduction.",
  "structured": { "material": "weathering_steel", "deck": "concrete", "cost_premium_pct": 8 },
  "produced_at": "..."
}
```

### 3.8 `design_specs`

```json
{
  "_id": "<auto>",
  "run_id": "...",
  "bridge_type": "multi-span_cable_stayed",
  "span_layout": [{"length_m": 200, "supports": ["pier", "pier"]} /*...10 spans...*/],
  "total_length_m": 2000,
  "deck_width_m": 12,
  "lanes": 2,
  "design_live_load_kN_per_m": 12,
  "primary_material": "weathering_steel",
  "deck_material": "concrete",
  "aesthetic_style": "modern_minimal",
  "validation_status": "pending"
}
```

### 3.9 `validation_results`, `cost_estimates`, `artifacts`

```json
// validation_results
{ "run_id": "...", "checks": [
    {"name": "span_to_depth_ratio", "status": "pass|warning|fail", "value": 8.3, "note": "..."},
    ...
  ],
  "overall_status": "conceptual_pass_with_warnings"
}

// cost_estimates
{ "run_id": "...", "currency": "EUR",
  "line_items": [
    {"item": "structural steel", "qty": 4200, "unit": "tonnes", "unit_cost": 3500, "subtotal": 14700000},
    ...
  ],
  "subtotal": 32400000, "contingency_pct": 15, "total": 38400000,
  "narrative": "..."
}

// artifacts
{ "run_id": "...", "kind": "engineering_schematic|architectural_elevation|final_report_md",
  "uri_or_inline": "...",          // for SVG/markdown, store inline; for image URL, store URL
  "created_at": "..."
}
```

### 3.10 `events`

```json
{ "run_id": "...", "ts": "...",
  "kind": "decompose|skill_search|coalition_formed|message_posted|subtask_completed|...",
  "payload": {/* small structured blob */} }
```

### 3.11 `reputation_updates`

```json
{ "run_id": "...", "agent_id": "...", "delta": +0.01, "reason": "selected_and_validation_passed" }
```

Indexes: `agent_id`, `run_id`.

---

## 4. Algorithms (Specifications, Not Code)

### 4.1 Decomposition

LLM call. Prompt the model to emit, given the user prompt and the current date:

```json
{
  "subtasks": [
    {"subtask_id": "T1", "title": "...", "description": "...",
     "required_capabilities": ["..."], "depends_on": []},
    ...
  ]
}
```

Constraints:
- Must produce 5–8 subtasks.
- DAG must be acyclic; depends_on may only reference earlier subtask_ids.
- Must include — when the user prompt implies a deliverable proposal — at least one subtask each for *validation*, *budget*, *visualization*, and *final report*.
- On JSON failure: retry once, then fall back to a deterministic default DAG hardcoded for the bridge use case.

### 4.2 Stage-1 dimensionality reduction (per subtask)

For each `required_capability` string `q`:
1. Embed `q` with `text-embedding-3-small`.
2. `$vectorSearch` on `skills` with `numCandidates=100`, `limit=8`. Optionally `$match` on `category in ["engineering","design","analysis"]`.
3. Union the result sets across capabilities → candidate skill set `C` (deduplicated, |C| ≤ 15).

### 4.3 Stage-2 pairwise-complementarity coalition

Given candidate set `C`:

For each skill `s ∈ C`, define **solo value**:
$$v(\{s\}) = \alpha \cdot \text{coverage}(s, q) + \beta \cdot \text{prior\_reputation}(s) + \gamma \cdot \log\,(1 + \text{installs}(s))$$
with `α=0.6, β=0.3, γ=0.1` (γ pre-normalised).

For each pair `(s_i, s_j)`, define **pairwise value**:
$$v(\{s_i, s_j\}) = v(\{s_i\}) + v(\{s_j\}) + \lambda \cdot (1 - \cos(\mathbf{e}_i, \mathbf{e}_j))$$
with `λ=0.4`. The `(1 - cos)` term is the **complementarity bonus** — high when embeddings are dissimilar (different skills) and low when redundant.

Greedy coalition formation:
1. Pick `s* = argmax v({s})` → coalition = `{s*}`.
2. While `|coalition| < 3`:
   - Find `s' = argmax v(coalition ∪ {s'}) − v(coalition)` (marginal contribution).
   - If marginal contribution `< τ` (threshold, default 0.05) → stop.
   - Else add `s'`.
3. Return coalition.

This is a **rank-1 Shapley approximation** because we only ever evaluate values of singletons and pairs, never triples or higher; the marginal contribution of a candidate to a 2-set is approximated by the maximum of its pairwise contributions to each member.

> See `GAME_THEORY_PRIMER.md` for the formal connection to induced subgraph games.

### 4.4 Skills → agents (set-cover)

Given coalition skill set `K`:
- For each agent, compute `cover(agent, K) = |skills(agent) ∩ K|`.
- Greedy set-cover: pick agent maximising `cover` weighted by `reputation`; remove its covered skills from `K`; repeat until `K` empty or 3 agents picked.
- Prefer polyvalent agents on ties (the "polyvalence bonus"): `score = cover · (1 + 0.05 · polyvalence) · reputation`.

### 4.5 Coalition execution (the blackboard protocol)

For each subtask `T` in topological order:

```
post_kickoff(T):
   marshal_prompt = render(
     subtask=T,
     coalition=agents,
     upstream_summaries = [subtask_outputs[u].summary for u in T.depends_on]
   )
   marshal_kickoff_text = LLM(marshal_prompt)
   coalition_messages.insert({
     run_id, subtask_id=T.id, ts=now(),
     sender="marshal", role="marshal", round=0,
     text=marshal_kickoff_text
   })

for agent in coalition (ordered by contribution_score desc):
   log_text = render_log(coalition_messages.find({subtask_id=T.id}).sort(ts))
   agent_prompt = render(agent_profile, subtask=T, log=log_text,
                         my_skills=agent.skills_in_coalition)
   contribution = LLM(agent_prompt)
   coalition_messages.insert({..., sender=agent.id, role="agent", round=1,
                              text=contribution.text, meta=contribution.meta})

reconcile(T):
   log_text = render_log(...)
   marshal_reconcile_prompt = render(
     log=log_text,
     instruction="Either consolidate into a final summary, OR identify ONE conflict and request ONE revision from one specific agent."
   )
   reconcile = LLM(marshal_reconcile_prompt)
   coalition_messages.insert({..., role="marshal", round=2, text=reconcile.text})
   if reconcile.requests_revision and not already_revised:
       run_revision(reconcile.target_agent)
       reconcile_again()
   subtask_outputs.insert({
     run_id, subtask_id=T.id,
     summary=reconcile.final_summary,        # ≤200 tokens, enforced
     structured=reconcile.structured_output
   })
```

Token-budget rule: **the only thing crossing subtask boundaries is `subtask_outputs.summary`**. Everything else stays in Mongo for the audit trail.

### 4.6 End-of-pipeline agents

Run in parallel after the last subtask completes:

- **Synthesizer** — LLM. Reads all `subtask_outputs.summary` for the run. Emits a single `design_specs` document.
- **Validator** — pure Python. Runs deterministic checks against the design spec (span/depth ratio, support count, load arithmetic, material-span plausibility). Writes `validation_results`.
- **Quantity Surveyor** — LLM-wrapped deterministic. A `cost_model.json` file defines unit costs (per-tonne steel, per-pier, deck-area, finishing premium). Python computes line items; LLM writes the narrative paragraph.
- **Visual Designer** — produces *two* artifacts:
   1. **Engineering schematic** — a Plotly elevation drawing with span markers, supports, dimensions, material legend, validation badge.
   2. **Architectural elevation** — a stylised SVG, see § 5.

- **Final Report agent** — LLM. Produces a markdown government-bid proposal that embeds: executive summary, design spec table, both visuals, validation card, budget table, agent provenance section ("delivered by coalition of N agents drawn from the skills.sh catalog"), conceptual disclaimer.

### 4.7 Reputation update

For each agent `a` participating in run `r`:
- If validation overall_status ∈ {`conceptual_pass`, `conceptual_pass_with_warnings`} → `Δ = +0.01`.
- If overall_status = `fail` and `a` was in a coalition whose subtask is implicated → `Δ = -0.02`.
- Clamp `reputation` to `[0, 1]`.
- Insert into `reputation_updates`; update `agents.reputation`.

---

## 5. Visualization Strategy (the WOW)

The user has explicitly asked for something *professional, not AI-generated, not CAD*. We deliver **two complementary views**, both produced programmatically.

### 5.1 Engineering schematic (Plotly)

Purpose: *prove the system understood the geometry it produced*.

- Wide elevation (16:9), clean white background, axis units in metres.
- Drawn elements:
   - water region (light blue rect with subtle hatch)
   - banks (dark grey wedges at both ends)
   - bridge deck (bold dark line with thickness from `deck_width_m` legend)
   - supports (vertical bars at each pier x-coordinate; abutments at ends)
   - main structural members (truss diagonals or cable stays — depends on bridge_type)
   - dimension callouts: total length, span lengths, deck width (using Plotly annotations with arrows)
   - material legend
   - validation status badge in corner
- Single colour palette: charcoal `#1f2933`, slate `#52606d`, water blue `#cbd2d9`, accent `#2563eb`.

### 5.2 Architectural elevation (SVG, hand-coded)

Purpose: *the WOW*. This is what makes a judge say "oh, they actually made an effort".

This is **not** an AI image. It is a **stylised SVG** assembled by a Python function. Inspirations: Le Corbusier presentation drawings, modern infrastructure firm portfolios (e.g., Knight Architects bridge concept sheets).

Layered SVG composition (back-to-front):
1. **Sky gradient** — `<linearGradient>` from warm pale yellow at horizon to soft blue at top (golden-hour palette).
2. **Distant mountains / city silhouette** — two or three layered SVG `<polygon>` paths in increasing darkness (parallax depth cue), seeded from a small library of silhouette vector paths chosen by `aesthetic_style`.
3. **Water plane** — pale blue `<rect>` with horizontal stripe pattern (`<line>`s at varying opacity to suggest reflection).
4. **River banks** — two `<path>` shapes, vegetation hint via small triangles for trees.
5. **Bridge structure** — generated from `design_spec`:
   - deck as a bold horizontal `<rect>` with subtle drop shadow (`<filter>` blur)
   - piers as tapered `<polygon>` (architectural taper, not just rectangles)
   - cable-stayed: fan or harp pattern of `<line>` elements from pylon top to deck
   - truss: top chord + diagonals
   - **light/shadow side**: every structural element duplicated and offset 2px with reduced opacity to simulate sun direction
6. **Foreground figures for scale** — a small SVG silhouette of a car or a pedestrian at deck level. Single instance, just enough to read scale instantly.
7. **Title block** — bottom-right, fixed-width font (`'IBM Plex Mono'` web-safe fallback `monospace`), four-line block:
   ```
   PROJECT  —  <run.title or generated name>
   TYPE     —  <bridge_type>
   LENGTH   —  <total_length_m> m
   STATUS   —  CONCEPTUAL DESIGN
   ```
8. **Disclaimer strip** — bottom-left, very small text, "Conceptual schematic. Not for construction."

Implementation: a single Python function `render_architectural_svg(design_spec: dict) -> str` using string templates. **No Pillow, no matplotlib for this output.** Pure SVG strings. The result is sharp at any zoom, looks intentional, and screenshot-ready for the judging slide.

### 5.3 Optional WOW++ — AI-rendered hero image

Only if time permits (after everything else works). One call to OpenAI's image API with a prompt assembled from the design spec. Saved to `artifacts`. Shown as a *third* tab labelled "Concept render" alongside the two SVG views. Easy to disable.

### 5.4 Why this beats AI-only

- Two views demonstrate a real pipeline: structured data → drawing.
- The SVG is parametric: change the prompt, the drawing changes coherently.
- Judges see provenance. AI image alone reads as decoration; SVG reads as *output*.

---

## 6. Streamlit UI Specification

Wide layout. Fixed top bar with app name + disclaimer banner.

### 6.1 Tabs

1. **Overview** — run metadata, key metrics, both visuals side-by-side, validation badge.
2. **Assignments** — three subsections: Tasks table; Assignments table with contribution scores and selection rationale; live event timeline. (Per Amendments 2026-05-01 the tab is named "Assignments"; it was "Agent Market" in earlier drafts.)
3. **Coalitions** — one collapsible card per subtask, each rendering its `coalition_messages` as a chat-style timeline (marshal in one colour, agents in another). This is the **direct visual answer** to the hackathon question about agent communication.
4. **Design** — design_spec table + engineering schematic.
5. **Validation** — validation cards, deterministic check results, warnings.
6. **Budget** — line-item table + bar chart by category.
7. **MongoDB Records** — five expandable raw-JSON viewers (skills sample, agents sample, this run's subtasks, this run's coalition_messages, this run's events). Mongo as the system of record, made literal.
8. **Final Report** — markdown render of the proposal.

### 6.2 Run controls

- prompt textarea (default: bridge prompt)
- toggle: *Use mock LLM* (default off after Phase 6)
- button: *Run Coalitions*
- button: *Replay last run from MongoDB* (reads everything from Mongo, no LLM calls — proves persistence)

### 6.3 Live progress

Use `st.status` with one entry per stage. Stream events as they're written.

---

## 7. Mock Mode (mandatory)

The demo must work end-to-end with no API calls. Set `USE_MOCK_LLM=true` and:
- decomposer returns the canonical 7-subtask DAG for any prompt
- agent contributions return short templated text scoped by skill name
- marshal returns templated kickoff and reconcile
- visualizations work identically (they don't depend on LLMs)
- validator and surveyor work identically

Mock mode is the *fallback if the OpenAI key fails during demo*. It must not be a second-class path.

---

## 8. Project Structure

```
.   # workspace root IS the project root (per Amendments 2026-05-01 #18)
├── README.md
├── pyproject.toml or requirements.txt
├── .env.example
├── data/
│   └── skills_seed.json              # ingested from skills.sh, ~150 skills
├── cost_model.json                   # unit costs for surveyor
├── src/
│   ├── __init__.py
│   ├── config.py                     # env loading, model names, Mongo URI
│   ├── db/
│   │   ├── client.py                 # singleton Mongo client
│   │   ├── indexes.py                # idempotent index creation incl. vector index
│   │   └── seed.py                   # load skills, synthesize agents
│   ├── llm/
│   │   ├── openai_client.py          # chat + embeddings + image
│   │   └── mock.py                   # deterministic mock for all roles
│   ├── decomposer.py
│   ├── matching.py                   # vector search + scoring
│   ├── coalitions.py                 # pairwise complementarity + greedy
│   ├── set_cover.py                  # skills → agents
│   ├── blackboard.py                 # post / read / render log
│   ├── marshal.py                    # kickoff + reconcile prompts
│   ├── execution.py                  # the per-subtask loop
│   ├── synthesis.py                  # final design spec
│   ├── validation.py                 # deterministic checks
│   ├── surveyor.py                   # cost computation + narrative
│   ├── visualizer/
│   │   ├── schematic_plotly.py
│   │   ├── architectural_svg.py
│   │   └── ai_render.py              # optional
│   ├── reporter.py                   # final markdown bid doc
│   ├── reputation.py
│   ├── orchestrator.py               # the LangGraph (or plain function) wiring
│   └── ui/
│       └── app.py                    # Streamlit
└── tests/
    ├── test_matching.py
    ├── test_coalitions.py
    ├── test_validation.py
    └── test_e2e_mock.py              # full pipeline in mock mode
```

---

## 9. Requirements for the Coding Agent

The coding agent **must** follow this section verbatim. Deviations require a written note in the PR description.

### 9.1 Hard constraints

1. **Single Python process.** No external services other than MongoDB Atlas and OpenAI.
2. **Python 3.10+.**
3. **Reproducible environment.** Create a dedicated conda environment (`environment.yml` checked into the repo, name `coalitions`) so teammates can clone and run with a single `conda env create -f environment.yml`. Pin major versions of `pymongo`, `openai`, `streamlit`, `plotly`, `python-dotenv`, `langgraph`, `tiktoken`. A `requirements.txt` mirror is fine but the conda env is the source of truth.
4. **All secrets via `.env` (python-dotenv).** Provide a tracked `.env.example` with placeholder values for `MONGODB_URI`, `MONGODB_DB`, `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL`, `USE_MOCK_LLM`. The real `.env` is gitignored. `src/config.py` is the single point of `load_dotenv()` and exposes typed config to the rest of the codebase. **No secret literal anywhere else in the source tree.**
5. **All Mongo writes idempotent on retry.** Use `run_id` as the partition key for everything.
6. **Mock mode is first-class.** Develop in mock mode first; LLMs come last.
7. **No 3D rendering. No CAD. No FEA. No engineering claims.**
8. **No raw outputs cross subtask boundaries.** Only `subtask_outputs.summary` does. Enforce a 200-token cap on summaries with truncation.
9. **All LLM calls return structured JSON with strict validation + 1 retry + mock fallback.**
10. **Disclaimer string** present in UI banner, final report header, and every artifact.
11. **Run twice during the demo** — second run must use updated reputations.
12. **Git is mandatory.** The repo must be a git repo from commit zero. The agent commits after every gate G1–G11 in §9.4 passes, with message format `gate Gx: <name>` (e.g. `gate G3: mongo connectivity`). The spec snapshot (`MVP_DESIGN.md` + `GAME_THEORY_PRIMER.md`) must be commit #1 before any code is written. The agent never uses `git push --force`, `git reset --hard` against shared history, or `--no-verify`. `.env` is gitignored; `.env.example` is tracked.

### 9.2 Build order (time-boxed)

| Phase | Deliverable | Hours |
|---|---|---|
| 1. Bootstrap | Conda env (`environment.yml`), project tree, `.env` + `.env.example`, Mongo connection check, indexes created | 0.5 |
| 2. Data layer | skills_seed.json prepared (manual or scrape), seed loader, agent synthesiser | 1.0 |
| 3. Mock pipeline | decomposer, matching, coalitions, set_cover, blackboard, mock marshal & agents, synthesis, validation, surveyor — fully working in mock mode end-to-end | 2.5 |
| 4. UI scaffold | Streamlit with all tabs reading mock-mode data | 1.5 |
| 5. Visuals | Plotly schematic + SVG architectural elevation | 1.5 |
| 6. Real LLMs | Wire OpenAI for decomposer, marshal, agents, synthesizer, surveyor narrative, final reporter | 1.5 |
| 7. Vector search | Embed skills, create Atlas vector index, replace keyword matching with `$vectorSearch` | 1.0 |
| 8. Reputation + replay + polish | Persistent reputation, replay-from-Mongo button, demo dress rehearsal | 1.0 |
| **Total** | | **10.5** |

If running out of time, cut in this order: AI hero render → vector search (fall back to embedding-cosine in Python) → reputation persistence demo → marshal reconcile round (kickoff only).

### 9.3 Acceptance criteria (the agent's "definition of done")

The MVP is shippable when **all** of the following hold:

1. Running `streamlit run src/ui/app.py` and clicking *Run Coalitions* with the default prompt completes in under 90 seconds in mock mode and under 5 minutes in LLM mode.
2. The Mongo `events` collection contains at least one event for every pipeline stage.
3. `coalition_messages` contains at least 12 messages for the default prompt across all subtasks.
4. `subtask_outputs.summary` is non-empty for every subtask and ≤ 200 tokens each.
5. The Coalitions tab visibly shows a chat-style log per subtask with marshal and agent turns distinguishable.
6. The MongoDB Records tab displays raw JSON for each documented collection.
7. Both visuals (Plotly schematic + SVG architectural elevation) render without error and reflect parameters from `design_specs`.
8. Validation, cost, and final report are all populated and visible.
9. *Replay from MongoDB* reproduces the UI state from a finished run with zero new LLM calls.
10. Two consecutive runs show different `agents.reputation` values for at least three agents.

### 9.4 Per-commit acceptance gates (for the coding agent's self-check)

The agent must work in small commits and tick off these gates **in order**. Each gate has a single concrete check the agent can run and verify before moving on. If a gate fails, the agent stops and reports — does not proceed.

| # | Gate | Pass check |
|---|------|-----------|
| G1 | Conda env reproducible | `conda env create -f environment.yml` succeeds on a clean shell; `conda activate coalitions && python -c "import pymongo, openai, streamlit, plotly, dotenv, langgraph, tiktoken"` exits 0. |
| G2 | Config + secrets wiring | `cp .env.example .env`, fill in MONGODB_URI + OPENAI_API_KEY, then `python -c "from src.config import settings; print(settings.mongodb_db)"` prints the db name. No secret literal anywhere outside `.env`. |
| G3 | Mongo connectivity | `python -m src.scripts.ping_mongo` connects, lists collections, creates the 11 collections + indexes from § 3, exits 0. |
| G4 | Skills ingested | `python -m src.scripts.ingest_skills` populates `skills` and `agents` from `skills_seed.json`; counts printed match the seed file. |
| G5 | Vector search live | `python -m src.scripts.test_vector_search "structural steel design"` returns ≥ 1 candidate with a similarity score. |
| G6 | Mock pipeline end-to-end | With `USE_MOCK_LLM=true`, `python -m src.run --prompt "design a 2 km bridge for 50 cars/h"` completes in < 30 s; `subtask_outputs` non-empty for every subtask; ≥ 12 rows in `coalition_messages`; every pipeline stage has an `events` row. |
| G7 | Real-LLM pipeline end-to-end | With `USE_MOCK_LLM=false`, same command completes in < 5 min; same invariants as G6. |
| G8 | Streamlit renders | `streamlit run src/ui/app.py` opens; clicking *Run Coalitions* with the default prompt populates all 8 tabs without errors; both visuals render. |
| G9 | Replay works | After a finished run, *Replay from MongoDB* reproduces the same UI state with zero new LLM calls (verify via OpenAI request log or by disabling the API key). |
| G10 | Reputation persists | Running the same prompt twice in a row leaves at least three `agents.reputation` values changed. |
| G11 | Demo script passes | The narration in § 10 plays through start-to-finish in under 90 seconds without manual intervention. |

The agent should treat this table as the single source of progress. **No gate may be skipped.** Acceptance criteria § 9.3 are the system-level "shippable" definition; § 9.4 is the per-commit ladder that gets there.

**Commit discipline.** After each gate passes its check, the agent runs `git add -A && git commit -m "gate Gx: <name>"` (e.g. `gate G6: mock pipeline end-to-end`) before starting the next gate. This guarantees every gate is an independent rewind point if a later gate breaks something.

### 9.5 Coding standards

- Type hints on all function signatures. `mypy --strict` is aspirational; do not block on it.
- One module per file (see § 8).
- No globals other than singleton clients (Mongo, OpenAI).
- Logging via `logging` module, level `INFO` default.
- Every Mongo write goes through a thin helper that also inserts an `events` row.
- All LLM prompt templates live in `src/prompts/*.txt` (one file per role) — judges should be able to read them.

### 9.6 What the coding agent must NOT do

- Do not invent skills not in `skills_seed.json`.
- Do not pass full agent outputs across subtasks (only summaries).
- Do not implement bidding LLM calls. The "contribution score" is computed deterministically by the orchestrator.
- Do not add authentication, rate limiting, or deployment scripts.
- Do not write tests beyond what § 11 specifies.
- Do not refactor `LangGraph` in or out without checking with the human; it is acceptable to start with a plain function-based orchestrator and only port to LangGraph once everything else works.

---

## 10. Demo Script (60–90 s)

> *"Multi-agent systems face a delegation problem. With many agents and overlapping skills, choosing the right team is combinatorial. We solve it with a centralised, capability-search-based delegation system on MongoDB Atlas — technically a one-sided matching mechanism."*
>
> *"I'll submit a brief: design a 2-kilometre bridge for 50 cars per hour. The system pulls real skills from the skills.sh catalog into MongoDB. An LLM decomposes the brief into seven subtasks. For each one, MongoDB Atlas Vector Search reduces hundreds of skills to a handful, and a pairwise-complementarity score — a rank-1 Shapley approximation — selects a coalition of two or three."*
>
> *"Each coalition collaborates on a Mongo-backed blackboard. An LLM marshal opens the discussion, agents post contributions, the marshal reconciles. The only thing that leaves the coalition is a 200-token summary — that is how we share context within token limits."*
>
> *"At the end we get a unified design spec, deterministic validation, a cost estimate, and two visuals: an engineering schematic and a stylised architectural elevation. Everything lives in MongoDB — including the agent reputations, which update at the end of every run. Watch — I'll run it again, and you'll see the coalition selections shift because reputations changed."*
>
> *"MongoDB is not just our database. It's the skills inventory, the assignment ledger, the blackboard message bus, the context store, and the audit trail. Five distinct roles in one system."*

---

## 11. Validation Strategy (CRITICAL)

This section is what your boss will read first. Validation is *not* "does it produce a bridge"; validation is *"does the delegation mechanism work, and how do we prove it"*. Three layers.

### 11.1 System-level acceptance (does the pipeline work?)

The ten acceptance criteria in § 9.3. These are pass/fail and must be checked before the demo.

### 11.2 Mechanism-level evaluation (does the delegation mechanism actually do something useful?)

This is the **scientific** validation. We explicitly answer the question: *"Is capability-search-plus-pairwise-complementarity selection better than naïve baselines?"*

We compare three selection strategies for the same prompt, executed in mock mode for determinism:

| Strategy | Description |
|---|---|
| **A. Random assignment** | For each subtask, pick `min(3, |agents|)` random agents. |
| **B. Top-by-reputation** | Pick the 3 highest-reputation agents regardless of skill. |
| **C. Our delegation mechanism** | Vector search → pairwise complementarity → greedy set-cover. |

Metrics computed automatically per run:

1. **Skill coverage** — fraction of `required_capabilities` of each subtask covered by the chosen coalition's union of skills. Mean across subtasks.
2. **Redundancy** — mean pairwise embedding cosine within coalitions (lower is better).
3. **Coalition size** — distribution.
4. **Validation pass rate** — what fraction of runs end in `conceptual_pass` or `conceptual_pass_with_warnings`.
5. **LLM token cost** — sum of prompt + completion tokens (in real-LLM mode only).
6. **Wall time** — end-to-end seconds.

We run each strategy ≥ 3 times per prompt (mock mode allows variance via random seeds for A) on at least two prompts:
- the bridge brief
- a deliberately mismatched brief (e.g., *"design a wooden footbridge across a 100m gorge"*) to stress-test robustness

A small results table goes into the *Overview* tab and the final report. **The story we want to tell is: C beats A on coverage, beats B on redundancy, and is competitive on cost.**

If the data shows otherwise, we say so. The honesty *is* the validation. Either the mechanism works, in which case we have a result; or it doesn't, in which case we have a finding.

### 11.3 Coalition-quality evaluation (LLM-as-judge)

For each subtask in a run, an external LLM judge (a separate model role, prompt-versioned and stored in `prompts/judge.txt`) scores the marshal's final summary on:
- *clarity* (0–10)
- *completeness against required_capabilities* (0–10)
- *internal consistency* (0–10)

The judge is given only the subtask description and the final summary — never the blackboard log, to avoid bias. Scores stored in `validation_results.judge_scores`. A small radar chart in the Validation tab visualises them.

### 11.4 What we deliberately do NOT validate

- We do **not** validate that the bridge would stand up. We are explicit about this.
- We do **not** claim cost estimates are accurate. They are plausible orders of magnitude based on a static `cost_model.json`.
- We do **not** benchmark against human designers. The comparison surface is *between selection strategies*, not against humans.

### 11.5 Reproducibility

Every run is fully reproducible from MongoDB:
- random seeds stored in `runs.config.seed`
- LLM responses optionally cached in `llm_cache` collection by prompt hash
- *Replay from MongoDB* button regenerates UI state with zero LLM calls
- `runs.config.git_sha` recorded if available

This addresses the most common reviewer complaint about LLM demos ("I can't reproduce that"). We can.

---

## 12. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| OpenAI quota exhausted mid-demo | medium | high | Mock mode is first-class fallback |
| Atlas vector index slow to build | medium | medium | Build at boot, keep N small (≤ 200) |
| Marshal LLM emits invalid JSON | medium | medium | Strict schema + 1 retry + deterministic fallback |
| Coalition reaches `redundant` 3-set | low | low | Threshold τ on marginal contribution stops greedy early |
| SVG renderer ugly | medium | high (demo) | Lock palette + typography early; review at Phase 5 mid-point |
| Total time blowout | high | high | Cut order in § 9.2; mock-mode happy path always demoable |

---

## 13. Definitions

- **Agent** — a profile in the `agents` collection. A skill bundle. Not a process.
- **Marshal** — a designated LLM role (one per coalition) responsible for kickoff, reconcile, and final summary. Marshals are themselves agents drawn from a small set of *coordinator-style* profiles.
- **Coalition** — the 1–3 agents selected to deliver one subtask.
- **Blackboard** — the `coalition_messages` collection, scoped by `(run_id, subtask_id)`. Conceptually a per-coalition append-only log.
- **Contribution score** — deterministic score computed by the orchestrator for each agent considered for assignment. Replaces the word "bid" everywhere.
- **Subtask summary** — the marshal-produced ≤ 200-token text that crosses subtask boundaries. The only such text. Stored in `subtask_outputs.summary`.

---

## 14. Sign-off

This document is the contract. The coding agent implements it as written. Deviations are flagged in writing.

**Reviewers (please sign):**
- [x] Lucia (lead) — amendments approved 2026-05-01
- [ ] Teammate 1
- [ ] Teammate 2

---

## Appendix A — On the word "market"

Earlier drafts called this system an *agent market* and described the selection step as *bidding*. That vocabulary is convenient for a 60-second pitch but it overstates what the system actually does. We are explicit about it here so that an econ-literate reviewer cannot fairly accuse us of inflating our claims.

### A.1 Why this is not a market in the economic sense

A market in the strict sense \u2014 the sense used in mechanism design and microeconomic theory \u2014 minimally requires:

1. **Multiple sides with private information.** Buyers and sellers each know things the other side does not.
2. **Voluntary participation and strategic agents.** Participants choose whether to enter and what to offer.
3. **Price discovery.** Value emerges from the interaction (auction, bid-ask spread, double auction), not from a fixed formula.
4. **Incentive compatibility (or an explicit account of misreporting).** A well-designed market either makes truth-telling optimal or analyses what happens when it isn't.
5. **Clearing under contested allocation.** Supply and demand resolve through the mechanism.

Our system has none of these:

| Property | Status in our system |
|---|---|
| Multiple sides w/ private information | All agent metadata is public in MongoDB; the orchestrator sees everything. |
| Voluntary participation, strategic agents | Agents do not decide. The orchestrator decides. |
| Price discovery | Contribution scores are computed by a fixed deterministic formula. There are no prices. |
| Incentive compatibility | Agents have no strategy space; they cannot misreport. |
| Clearing | Sort-of: not all candidates win, but there is no scarcity, no congestion, no price. |

Calling this a "market" therefore leans on a vocabulary we have not earned. We removed bidding theatre during methodology design exactly to avoid pretending otherwise.

### A.2 What it actually is

Three increasingly precise names:

1. **Capability-search-based delegation system** — plain English. This is the title of the document.
2. **Centralised one-sided matching mechanism with a structured scoring rule** — the academic framing.
3. **Coordinator-mediated coalition formation pipeline using cooperative-game-theoretic selection** — the most technically precise.

The closest legitimate analogy is the family of **one-sided matching markets** studied by Roth, Sönmez, and Ünver — work that earned Alvin Roth and Lloyd Shapley the 2012 Nobel Prize in Economic Sciences. In one-sided matching, a central planner allocates indivisible items (e.g., school seats, kidneys, dorm rooms) to agents based on declared preferences and a structured rule. There are no prices and no money. Such mechanisms are routinely called *markets* in the literature — the *kidney exchange market*, the *school choice market* — even though no money changes hands. The word *market* in that tradition denotes a centralised allocation mechanism, not a price-discovery institution.

Our system fits the same shape:

- **Items being allocated:** subtasks (one item per subtask).
- **Agents:** skill bundles.
- **Declared preferences:** none in our v1; replaced by a deterministic compatibility score derived from skill embeddings, prior reputation, and pairwise complementarity.
- **Centralised rule:** vector search → pairwise-complementarity coalition formation → greedy set-cover.
- **No money, no prices, no strategic reporting.**

This is the framing we use when challenged.

### A.3 Where we previously used the word "market"

Earlier drafts kept *market* in three places, all colloquial: the Streamlit tab name "Agent Market", the run-button label "Run Agent Market", and the database / project directory name `agent_market`. **As of Amendments 2026-05-01 these are all renamed** (tab → "Assignments", button → "Run Coalitions", DB → `agent_coalitions`, repo layout uses the workspace root). The word *market* survives in this document only as historical / philosophical discussion of why we don't use it.

### A.4 What it would take to legitimately call this a market

For completeness, the smallest extension that would make "market" defensible:

- Give each agent a **strategy space** — e.g., a `declared_confidence` value submitted before scoring.
- Make the orchestrator's selection depend on declared confidence.
- Penalise over-claiming after the fact by comparing declared confidence to the LLM-judge's score on the agent's contribution, and feed the discrepancy back into reputation.

That is a *truthful-reporting incentive mechanism*, the minimum content to justify the word. It is roughly an extra hour of work and we may add it as a stretch goal. Until then, we use the more honest term.

### A.5 Suggested reading

- Roth, A. E. (2002). *The Economist as Engineer: Game Theory, Experimentation, and Computation as Tools for Design Economics.* Econometrica, 70(4).
- Roth, A. E., Sönmez, T., & Ünver, M. U. (2004). *Kidney exchange.* Quarterly Journal of Economics, 119(2).
- Abdulkadiroğlu, A., & Sönmez, T. (2003). *School choice: A mechanism design approach.* American Economic Review, 93(3).
- Hatfield, J. W., & Milgrom, P. R. (2005). *Matching with contracts.* American Economic Review, 95(4).

For our purposes the single best entry point is Roth (2002): it makes the case that *market design* is a discipline of building rules to allocate scarce things, and explicitly includes mechanisms without prices. That is the lineage we sit in — not the lineage of stock exchanges or auction houses.

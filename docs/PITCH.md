# Pitch — Agent Coalitions

> **Project name:** **Agent Coalitions**
> **Hackathon:** MongoDB London — Multi-Agent Collaboration track
> **Slot:** 5 minutes (presentation) + Q&A
> **Repo:** [/Users/lucia/Desktop/Hackathon_MongoDB](../)

This document is the literal script + stage directions for a 5-minute
demo. Read it twice, then deliver from the bullet outline at the end.
Word counts assume ~150 wpm spoken pace (a confident-but-not-rushed
delivery), which gives ~750 words of speech in 5 min. Everything here
is true to the implementation; no marketing hype that the code can't
back up.

---

## 1. The 30-second elevator pitch

> *"Agent Coalitions takes a free-text engineering brief — like 'design
> a 2 km bridge for 50 cars an hour' — and assembles a team of
> specialised AI agents to design it. The interesting part isn't that
> the agents talk to each other; it's how the team is **chosen**.
> MongoDB Atlas Vector Search finds candidate skills, and a
> Shapley-style cooperative-game algorithm picks the **most
> complementary** agents — not the most relevant ones, the most
> complementary. MongoDB plays five distinct roles: skills inventory,
> assignment ledger, blackboard message bus, cross-subtask context
> store, and persistent reputation memory. Remove MongoDB, you
> remove five capabilities, not one."*

That's the pitch you give if someone stops you in a corridor. The
5-minute version expands each idea below.

---

## 2. The 5-minute script (timed)

### Minute 1 — The problem (≈150 words, ~60 s)

*Open on the Streamlit app, default prompt visible.*

> "The hackathon track asks: how do agents **convey their skills**,
> **identify suitable peers** for a sub-task, **share context**
> within token limits, and **collaborate** on intricate tasks. Most
> answers to that prompt look like 'a router LLM picks the top-3
> agents by name'. That's a chatbot, not a team.
>
> The harder question — the one we picked — is **how do you pick a
> good team, not just a relevant team?** Two material scientists who
> know the same things are not a team; they're one expert with a
> spare. A team is a group whose skills **complement** each other.
> That's a problem from cooperative game theory, and the maths has
> existed since 1994.
>
> So our brief is: take a free-text design requirement, build a
> coalition that maximises pairwise complementarity, run it, and
> ship a defensible engineering report — with MongoDB doing the
> structural work."

### Minute 2 — The architecture (≈150 words, ~60 s)

*Click the **🕷️ Workflow** tab if on the LangGraph branch — it shows
the 9-stage Mermaid diagram. Otherwise click **🌳 DAG** to show the
subtask DAG.*

> "Nine stages. Decompose the brief into a subtask DAG. For each
> subtask, embed its required capabilities, query **Atlas Vector
> Search** on a 1536-dimension cosine index over the skills
> catalog, then run a **coalition formation** step — that's the
> game theory — to pick at most three skills. A set-cover step
> turns those skills into at most three concrete agents. The
> agents then collaborate on an **append-only blackboard**
> persisted to MongoDB — three rounds: marshal kickoff, parallel
> contributions, marshal reconcile, capped at a 200-token summary
> per subtask. Downstream subtasks read upstream summaries
> from MongoDB. Synthesise, validate, cost-estimate, render, write
> a report. **Replay** the whole run from MongoDB with zero LLM
> calls. That's our G9 invariant — the assignment ledger isn't a
> log, it's the source of truth."

### Minute 3 — The actually-interesting bit: how the team is picked (≈150 words, ~60 s)

*Click the **👥 Teams** tab and pick a subtask. Point at the Shapley
column.*

> "Each candidate skill gets a **solo value**: 60% semantic match
> against the requirement, 30% prior reputation from
> installs and stars, 10% popularity. Then we add a **pairwise
> complementarity bonus** — for any two skills $i$ and $j$, we add
> a term proportional to $1 - \cos(e_i, e_j)$ — the more *different*
> they are, the more we reward putting them together. That's an
> **induced-subgraph cooperative game**, Deng-Papadimitriou 1994. For
> games of that exact shape there is a closed-form Shapley value:
> $\varphi_i = a_i + \tfrac{1}{2}\sum_{j} w_{ij}$. We display it in
> the UI as `shapley` and `contribution %`. Replace the algorithm
> with 'top-3 by cosine' and you get three near-identical experts.
> This is the move that turns the system from a chatbot into a
> team-builder."

### Minute 4 — MongoDB, the five roles (≈150 words, ~60 s)

*Click whichever tab makes the relevant collection visible (Agent
comms tab → coalition_messages; Reputation tab → reputation_updates).*

> "MongoDB Atlas isn't a sidecar here, it's load-bearing in five
> distinct ways:
>
> One — **vector search** on the skills catalog with the Atlas
> `$vectorSearch` aggregation stage; 1536-d cosine index, native.
>
> Two — **catalog**: 36 skills, 21 agents with skill_ids; ordinary
> documents with B-tree indexes.
>
> Three — **message bus**: every blackboard turn is an append-only
> document, indexed by `(run_id, subtask_id, ts)`. The orchestrator
> reads from it; agents write to it. No queues, no Redis.
>
> Four — **cross-subtask context store**: the 200-token summaries
> live as `subtask_outputs` documents — that's the only thing that
> crosses subtask boundaries.
>
> Five — **persistent reputation**: `agents.reputation` is mutated
> per run; results carry to the *next* prompt. Every other tab in the
> UI is a `find()` against that ledger.
>
> Pull MongoDB out, and **five capabilities disappear**, not one."

### Minute 5 — The demo: end-to-end run (≈150 words, ~60 s)

*Click "Run Coalitions" with the default prompt (mock LLM mode for
speed and reproducibility). The pipeline finishes in ~5 s.*

> "Watch — five seconds, mock mode. Real LLM mode is ~30 s, same
> structure. Twelve subtasks, twenty-one possible agents, the
> coalition picks itself. Here's the **3D rendering** — the
> visualiser stage emits domain-agnostic geometric primitives, the
> renderer is dumb. Here's the **AI concept render** — optional,
> one click, OpenAI image API in real mode, deterministic SVG
> placeholder in mock mode so the demo never blanks out. Here's
> the **Report**, government-bid-style: introduction, validation
> table, cost breakdown, disclaimer. And here's the **Replay**
> button — same `run_id`, zero LLM calls, byte-identical UI.
> Because everything is in MongoDB. That's the system. Ask me
> anything."

---

## 3. Bullet outline (the version you actually deliver from)

Print this on a single sheet of paper, glance at it once per minute.

| Min | Tab | Beat | Key phrase |
| --- | --- | --- | --- |
| 1 | Default | The problem isn't routing, it's team-building | *"a relevant team is not a good team"* |
| 2 | Workflow / DAG | 9-stage pipeline, Atlas Vector Search → coalition → blackboard → report → replay | *"replay with zero LLM calls"* |
| 3 | Teams | Shapley closed form on an induced-subgraph game | *"complementarity, not relevance"* |
| 4 | Comms / Reputation | MongoDB plays 5 distinct roles | *"remove Mongo, lose 5 capabilities"* |
| 5 | Run + Report + Replay | Live end-to-end in 5 s | *"the assignment ledger is the source of truth"* |

---

## 4. Q&A — likely questions and tight answers

These are the questions a technical judge actually asks. Each answer
is ≤ 30 seconds. None of them require improvising.

**Q: Is this just RAG?**
> No. Step 3 is RAG-shaped — embed query, vector-search Atlas, take
> top-k. But the retrieved skills **never enter an LLM prompt**.
> They feed a value function and a set-cover algorithm. The LLM
> never sees the skill catalog. It is *vector retrieval as the
> relevance signal in a combinatorial optimisation*, not RAG.
> *(Long answer in [docs/MATCHING_PIPELINE.md §"Is this RAG?"](MATCHING_PIPELINE.md).)*

**Q: Why not just use the top-3 by cosine similarity?**
> Two failure modes. Near-duplicates — three near-identical skills
> get identical cosines and you pick three carbon copies. And
> off-topic skills with strong priors. The coverage floor (cosine
> > 0.30) plus the complementarity bonus fix both. We have a
> reproducible failure where `propulsion-systems` was being picked
> for a bridge subtask before the floor was added.

**Q: Why LangGraph?**
> Honestly? On the master branch we don't use it. The `langgraph`
> branch has a parallel implementation behind a feature flag, with a
> Mermaid-diagram tab. At our current 9-node linear graph it's
> mostly decorative. It would earn its keep at scale via parallel
> `Send` fan-out over subtasks, conditional retry edges, and
> checkpointers — none of which we use yet. We documented the
> honest trade-off in [docs/LANGGRAPH.md §7](LANGGRAPH.md).

**Q: How big is the skills catalog?**
> 36 hand-curated skills + 21 agents in the demo seed. The TODO is
> to swap to ~150 entries scraped from skills.sh, the real public
> catalog. The pipeline is shape-agnostic — it does not care
> whether N=36 or N=10,000. Atlas Vector Search makes that boring.

**Q: What's the cost?**
> Mock mode: free, ~5 s. Real LLM mode: about 4 cents per subtask
> (one marshal + three agents per blackboard round) plus one
> decompose call. A 7-subtask brief costs ~30 cents end-to-end.
> The image hero render is ~5–10 cents extra and on-demand.

**Q: Could two coalitions form simultaneously?**
> Today no — the orchestrator iterates subtasks in topological
> order. Independent subtasks could fan out in parallel; the
> obvious win is doing that via LangGraph's `Send` API. It's a
> documented next step. Wall-clock would drop from
> $\sum_{\text{subtasks}}$ to $\max_{\text{subtasks}}$.

**Q: Where's the "memory" across runs?**
> `agents.reputation`. Every run updates it per agent based on
> validation outcome × load × quality. Run a second prompt and
> watch the reputation column move. It's the *only* state that
> survives across runs by design.

**Q: How do you know the validation is real?**
> Five static structural checks in `src/pipeline/validation.py`:
> span-to-depth ratio, support count consistency, live-load
> arithmetic, material-span plausibility, lane geometry. Pure
> Python, no LLM. The LLM judge layer (clarity, completeness,
> consistency) sits **on top** of those — and its scores show in
> the radar chart. The disclaimer is honest: *"Conceptual design
> produced by an experimental multi-agent system. Not certified
> engineering."*

**Q: What if I disagree with the team it picked?**
> Click "Run Coalitions" again with a tweaked prompt. Or fork the
> code and change the value function — `v(S)` lives in one place,
> `src/pipeline/coalition.py`. The 0.6 / 0.3 / 0.1 weights and the
> λ=0.4 complementarity weight are knobs we exposed deliberately.

---

## 5. Stage directions

- **Set-up.** Run `streamlit run app.py` ahead of time. Mock-LLM mode
  on (the default — keeps the demo deterministic and free). Sidebar
  collapsed; default prompt visible.
- **Backup.** A pre-recorded 90-second video of a real-LLM-mode run.
  Pull it up only if the live demo fails. Don't apologise; pivot.
- **Don't.** Don't say "agentic". Don't say "AGI". Don't say
  "production-ready". Don't promise things the disclaimer denies.
- **Do.** Show the Replay button. Show the Reputation tab on a second
  run. Both are extremely easy to demo and cheap to explain.
- **The honest closer.** *"This is one day of build. The maths is
  from 1994. The infrastructure is one Atlas cluster. The reason
  it works is that we let MongoDB do five jobs instead of one."*

---

## 6. Sources & deeper reading

- [docs/MVP_DESIGN.md](MVP_DESIGN.md) — the locked spec
- [docs/MATCHING_PIPELINE.md](MATCHING_PIPELINE.md) — the 9-stage data flow
- [docs/GAME_THEORY_PRIMER.md](GAME_THEORY_PRIMER.md) — Shapley closed form derivation
- [docs/TEAMS_TAB.md](TEAMS_TAB.md) — what each UI column means
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — the broader system view
- [docs/LANGGRAPH.md §7](LANGGRAPH.md) — the honest LangGraph self-assessment

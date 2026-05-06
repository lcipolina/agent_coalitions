# The matching pipeline — from a free-text prompt to a working team

> *"How does the methodology actually pick a team?"*

This document is the single overview of the system. Every other doc
in `docs/` zooms in on one piece; this one shows the whole flow on a
single page so you (or a judge) can read it in 90 seconds.

---

## TL;DR — one sentence

> A free-text **prompt** is split by an LLM into subtasks; each
> subtask's *required capabilities* are embedded with OpenAI and sent
> to a **MongoDB Atlas Vector Search** index of skills (1536-dim
> cosine). The top semantic matches are filtered through a
> **coverage floor** and a **greedy coalition step** that maximises a
> Shapley-style value function, then a **set-cover step** picks ≤ 3
> concrete agents that own those skills. MongoDB plays *five*
> distinct roles across that pipeline.

---

## The big picture — `prompt → vectorisation → cosine → Shapley → assignment`

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        USER PROMPT (free text)                         │
   │   "design a bridge for 50 cars/h, classic victorian, elegant"          │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
   ┌──────────────────────── 1. DECOMPOSER (LLM) ──────────────────────────┐
   │  Splits the prompt into a DAG of subtasks T1 … Tn.                    │
   │  Each subtask carries a list of `required_capabilities` (free text).  │
   │  e.g.  T3 "Material selection":                                        │
   │        ["material strength under cyclic load",                         │
   │         "compatibility with victorian aesthetics", …]                  │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼  (per subtask, per capability)
   ┌──────────────────── 2. EMBED (OpenAI / mock) ─────────────────────────┐
   │  Prompt-anchor:  "<full prompt>\n<capability>"                         │
   │  text-embedding-3-small  ──►  1536-dim float32 vector  q              │
   │  Cached per process so repeated capabilities are free.                │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   query vector q
                                  ▼
   ┌────────── 3. ATLAS VECTOR SEARCH  (MongoDB role #1) ─────────────────┐
   │  db.skills.aggregate([                                               │
   │    { $vectorSearch: {                                                │
   │        index: "skills_embedding_vector",                             │
   │        path:  "embedding",     // 1536-d, cosine                     │
   │        queryVector: q,                                               │
   │        numCandidates: 100, limit: 8                                  │
   │    }}                                                                │
   │  ])                                                                  │
   │  → top 8 skills closest to q, ranked by cosine.                      │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   candidate skills (~15 after dedup)
                                  ▼
   ┌────────────────── 4. EXACT COSINE + COVERAGE FLOOR ──────────────────┐
   │  re-load each candidate's full-precision embedding from MongoDB,     │
   │  compute exact NumPy cosine vs q  →  coverage(s, q) ∈ [0,1]          │
   │  drop any candidate whose coverage < 0.40                             │
   │  → "must be at least loosely on-topic" before priors get a vote.     │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
   ┌──────── 5. GREEDY COALITION  (Shapley-style team formation) ──────────┐
   │  For each candidate skill s:                                          │
   │    aᵢ = v({s}) = 0.6·coverage  +  0.3·prior_rep                       │
   │                  +  0.1·log(1+installs)/max_log_installs              │
   │                                                                       │
   │  Build the team greedily, capped at 3 skills:                         │
   │    1. seed with arg max  aᵢ                                            │
   │    2. while |team| < 3:                                               │
   │         add the candidate with the largest                            │
   │         marginal contribution  Δv = v(S∪{c}) − v(S)                   │
   │       stop early if Δv < τ (= 0.05).                                   │
   │                                                                       │
   │  Pairwise complementarity in v():                                     │
   │    v(S) = Σᵢ aᵢ  +  Σᵢ<ⱼ  λ·(1 − cos(eᵢ, eⱼ))                          │
   │           ───────                       ───────                       │
   │             solo                edge weight wᵢⱼ (λ = 0.4)             │
   │                                                                       │
   │  This is an **induced-subgraph game** (Deng–Papadimitriou 1994).      │
   │  It admits a closed-form Shapley value:                               │
   │       φᵢ = aᵢ + ½·Σⱼ wᵢⱼ                                               │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   skill team  S  (≤ 3 skills)
                                  ▼
   ┌────────── 6. SET-COVER → AGENTS  (MongoDB role #2: catalog) ──────────┐
   │  Find ≤ 3 agents whose `skill_ids` collectively cover S.              │
   │  Greedy weighted set-cover (ln |S| approximation):                    │
   │    score(a) = polyvalence(a)·0.4 + reputation(a)·0.6                  │
   │  At each step pick the agent that covers the most still-uncovered    │
   │  skills with the best score.                                          │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   ≤ 3-agent team
                                  ▼
   ┌────────── 7. COMMUNICATION FORUM  (MongoDB role #3: message bus) ───────┐
   │  Three rounds, persisted to `coalition_messages`:                     │
   │    round 0: marshal kickoff (the brief)                               │
   │    round 1: parallel agent contributions                              │
   │    round 2: marshal reconcile  → 200-token  `subtask_outputs.summary` │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
   ┌────────── 8. CREDIT  (Shapley closed form, displayed in UI) ──────────┐
   │  For each member of S we compute the exact Shapley value              │
   │     φᵢ = aᵢ + ½·Σⱼ≠ᵢ  wᵢⱼ                                              │
   │  and the normalised share φᵢ / Σ φⱼ × 100 %                            │
   │  → shown in the Teams tab as `shapley` (rounded to 2 dp) and          │
   │    `contribution %` (a.k.a. normalised Shapley / share of credit).    │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
   ┌────────── 9. REPUTATION  (MongoDB role #4: persistent memory) ────────┐
   │  base = +0.04 / +0.02 / −0.04  by validation outcome                  │
   │  load_factor   = subtasks_participated / total                       │
   │  quality_factor = mean of solo values aᵢ over contributed skills     │
   │  delta = base · (0.5 + 0.5·load) · (0.5 + 0.5·quality)               │
   │  Persisted on `agents.reputation` so it carries across runs.         │
   └────────────────────────────────────────────────────────────────────────┘
```

(MongoDB role #5 is the **assignment ledger** — every team that
forms is persisted to the `assignments` collection, which is what
makes the Replay button possible at all and what every UI tab reads
from. It is implicit in steps 5–9.)

---

## The "MongoDB does five things" cheat-sheet

| MongoDB role | Collection / index | What it stores | Step in the pipeline |
| --- | --- | --- | --- |
| **1. Vector search** | `skills` + Atlas index `skills_embedding_vector` | 70 skills × 1536-d embeddings, cosine | Step 3 |
| **2. Catalog** | `skills`, `agents` | Skill metadata, agent rosters with `skill_ids` | Steps 5–6 |
| **3. Message bus** | `coalition_messages` | Append-only communication forum, indexed `(run_id, subtask_id, ts)` | Step 7 |
| **4. Persistent memory** | `agents.reputation`, `reputation_updates` | Per-run delta + running reputation across all runs | Step 9 |
| **5. Assignment ledger** | `assignments`, `subtasks`, `subtask_outputs`, `runs` | Every team formed, every output, every cost — the replay surface | Steps 5–9 |

Removing MongoDB removes **five** capabilities, not one. That is
the point.

---

# Section A — The skill catalog (catalog construction)

Before any prompt arrives, the database must already contain a
catalog of skills *and* a roster of agents. This section explains
how that catalog is built, how every skill is guaranteed to be
carried by at least one agent, and how a future version could
ingest skills from the public **skills.sh** marketplace.

## A.0 Why have a catalog at all? (the methodological problem)

A reasonable first reaction is: *"why pick skills out of a
pre-existing catalog and then map them onto pre-existing agents?
Why not just ask an LLM to spawn an agent with exactly the skills
each subtask needs?"*

Our methodology solves the problem: — *"how do agents convey their skills, identify
suitable peers for a sub-task, share context within token limits,
and collaborate"* — only makes sense if **agents pre-exist the
prompt** as persistent entities. Five concrete things break the
moment you abandon that constraint:

1. **Persistent reputation.** `agents.reputation` is mutated at the
   end of every run and carries to the *next* prompt.
   If agents are spun up on demand they have no history to reward
   or punish, and every run starts from a blank slate. The
   marketplace + persistent agent roster is the substrate that
   makes reputation a meaningful signal at all.

2. **A real team-formation problem.** Coalition formation only
   matters when the candidate pool is **fixed**. If we could
   synthesise whatever we wanted, the optimal coalition is
   trivially "spawn N copies of the perfect specialist" and the
   Shapley math is decoration. The induced-subgraph game is
   interesting precisely because the agents you have to work with
   are *given*, not chosen.

3. **Complementarity has to exist before it can be measured.** Two
   agents complement each other when their skill sets differ in
   interesting ways. If we synthesise an agent's skill set after
   seeing the subtask, we are picking the answer first and the
   question second — `wᵢⱼ = 0.4·(1 − cos(eᵢ, eⱼ))` becomes a
   tautology because we chose `eⱼ` to be far from `eᵢ`.

4. **Scarcity is what makes set-cover non-trivial.** Step 6
   (greedy weighted set-cover, skills → agents) only does work
   because skills are unevenly distributed across agents and a
   single agent typically covers several chosen skills at once.
   With bespoke spawning, each skill maps 1:1 to a fresh agent and
   set-cover becomes the identity function.

5. **The catalog and the agents move at different speeds.** The
   skill marketplace is a slow-moving. Agents are the *consumers* of that marketplace: stable, persistent identities that have learned which skills
   they own and how well they perform with them. Conflating
   "spawn agent" with "pick skills" erases the marketplace
   entirely and with it MongoDB roles 2, 4, and 5 from the
   cheat-sheet above.

The pipeline is therefore deliberately split into two stages:

```
required capabilities  ──►  pick SKILLS   (steps 3–5: vector search + coalition)
                        │
                        ▼
       chosen skills    ──►  pick AGENTS  (step 6: set-cover over an existing roster)
```

This methodology offers us a system with audit trail, Shapley credit and persistent reputation.

## A.1 What's in the catalog

The skill catalog lives in
[`data/skills_seed.json`](../data/skills_seed.json) — 70 skills as
of this writing. Each entry follows this shape:

```json
{
  "skill_id": "cable-stayed-bridge-systems",
  "name": "Cable-Stayed Bridge Systems",
  "category": "engineering",
  "description": "Design and analysis of cable-stayed bridges …",
  "tags": ["cable-stayed", "bridge", "civil"],
  "prior_reputation": 0.86,
  "weekly_installs": 7400,
  "embedding": [0.0123, -0.0451, 0.0089, …]   // 1536 floats, persisted
}
```

When the seed script runs, every skill is converted to a single
short paragraph — its `name`, `description`, and `tags` joined — and
that paragraph is sent to OpenAI's
**`text-embedding-3-small`** endpoint via the official `openai`
SDK. The model returns a 1536-dimensional float vector, which is
written to `skills.embedding`. After seeding, the marketplace lives
in MongoDB as a set of pre-computed 1536-d points; an Atlas Vector
Search index named `skills_embedding_vector` (`type:
"vectorSearch"`, `numDimensions: 1536`, `similarity: "cosine"`)
builds an HNSW graph over that field for sub-millisecond
nearest-neighbour lookup.

The catalog is therefore *vectorised at rest*: at query time we
never re-embed it; only the query vector is fresh. This makes
retrieval pure server-side aggregation, makes runs replayable
(fixed catalog + fixed query → identical neighbours), and keeps
embedding cost to roughly $0.0001 in total once.

Code: [`src/db/seed.py`](../src/db/seed.py),
[`src/db/indexes.py`](../src/db/indexes.py).

## A.2 The full-coverage invariant

The pipeline has two related layers:

1. **Coalition formation** picks the *skills* a team needs (steps
   3–5 above).
2. **Set-cover** picks the *agents* that carry those skills (step 6).

If a chosen skill is **not held by any agent**, the set-cover step
has nothing to assign it to. Downstream the *Skills selected* table
in the Teams tab would show `assigned_to = —` and the marshal-
fallback agent would silently absorb the work. That looks broken,
even though the math is internally consistent. So we enforce a hard
invariant during seeding:

> **Every skill in the catalog must be carried by at least one
> agent.**

The arithmetic constraint is simple — the total *skill-slots*
across all agents must be `≥` the number of skills:

```
sum(AGENT_SKILL_DISTRIBUTION) >= len(skills)
```

A **slot** is one *(agent, skill)* assignment — i.e. the right of one
agent to carry one skill. Each agent is born with a fixed number of
slots (its capacity), and the seeder fills those slots with skill ids
during the coverage pass.

The current capacity vector is

```
AGENT_SKILL_DISTRIBUTION = [3]·10 + [4]·8 + [5]·2
```

— 10 agents have 3 slots each, 8 have 4, and 2 have 5 — for **20
agents** and `30 + 32 + 10 = 72` total slots. The catalog contains
**70 skills**, so

```
72 slots − 70 skills = 2 slack slots
```

The 70 skills are placed first (one per slot), guaranteeing every
skill is held by *at least* one agent. The 2 leftover slots are
**slack**: they get filled with duplicates of already-placed skills,
so two skills end up held by *two* agents each. That redundancy is
optional — the invariant only requires `slack ≥ 0`.

For contrast, the previous distribution `[2]·14 + [3]·4 + [4]·2 = 48`
gave only 48 slots for 70 skills — `slack = −22`. There was no way
to assign every skill to an agent, so the *Skills selected* table in
the Teams tab kept showing `agent_assigned = —` for whichever skills
had been left out. The seeder now raises `RuntimeError` the moment
it detects `total_slots < len(skills)`, before any data is written.

## A.3 The seeding algorithm (deterministic, 25 lines)

Implemented in [`src/db/seed.py::seed_agents`](../src/db/seed.py):

1. **Sanity check.** Read all skills from Mongo. If
   `sum(AGENT_SKILL_DISTRIBUTION) < len(skills)` → raise.
2. **Coverage pass (round-robin).**
   - Shuffle the skill list deterministically with `settings.seed`.
   - Walk the skills one by one; drop each into the next agent that
     still has a free slot.
   - Modulo-step through agents. After this pass, every skill is
     held by exactly one agent and `total_slots − len(skills)`
     slots remain free.
3. **Random-fill pass.** For any agent with free slots, sample
   additional skills from the catalog (excluding ones it already
   has). This adds redundancy: a few skills end up with two
   carriers, which the set-cover algorithm exploits when forming
   small teams.

Both passes use `random.Random(settings.seed)` so reseeding from
the same `seed` produces the same agent rosters — the demo is
reproducible.

After seeding, the *Skills selected* table never shows `—` in the
`agent_assigned` column for catalog skills; if you ever see one,
that's a real bug. (See [TEAMS_TAB.md](TEAMS_TAB.md).)

---

# Section B — Decomposer: prompt → DAG of subtasks

The first LLM call splits the user's free-text prompt into a
directed-acyclic graph of subtasks, each with:

- a `title` and `description`,
- a list of `required_capabilities` (free text, ~2 per subtask),
- a `depends_on` list of upstream subtasks,
- a topological index used by the orchestrator.

This is a single `gpt-4o` call against
[`src/llm/prompts/decomposer.md`](../src/llm/prompts/decomposer.md).
Its output is the only thing that drives all downstream retrieval —
the literal phrasing of `required_capabilities` is what enters the
embedder. (This is also why "site analysis" produces a different
team than "geotechnical site investigation" — the wording matters.)

---

# Section C — Embed & vector search

This is the most important step in the pipeline to get right, and
it is the one most often hand-waved in agent-system papers, so the
full chain is spelled out here.

## C.1 Which embedding model, and where does it run?

We do **not** use a local embedding library
(Sentence-Transformers, HuggingFace `transformers`, FastEmbed). We
use a *hosted* embedding model: **OpenAI's
`text-embedding-3-small`**, accessed over HTTPS through the
`openai` Python SDK.

OpenAI publishes two families of models on the same API: chat
models such as `gpt-4o-mini` (autoregressive decoders that emit
text) and embedding models such as `text-embedding-3-small`
(transformer encoders that emit a fixed-size vector). We use both:
chat models for the decomposer, the marshals, the agents, and the
synthesiser; the embedding model only for the retrieval layer
described here. The embedding endpoint returns 1536 float-32 values
per input string; nothing about the model weights ever runs
locally.

The reason for picking the hosted model over an open-source one is
empirical: the catalog is full of short, technical phrases like
*"cable-stayed bridge systems"* and *"aerodynamics and CFD"*, and
OpenAI's third-generation embeddings give noticeably cleaner cosine
separation between domains than the small open-source models
commonly used in tutorials. The trade-off is a network call per
query and a small per-token cost — negligible at hackathon scale
(~70 catalog embeddings + a handful of query embeddings per run,
well under one cent in total).

## C.2 Prompt-anchored query strings

When a run starts, the decomposer produces subtasks each carrying
a list of free-text required capabilities (e.g. T1 "Site &
geometry" might need *"site planning"*, *"geometry"*,
*"alignment"*). For every capability we build a **prompt-anchored
query string** by concatenating the run's full prompt with the
capability:

```
"design a 2 km bridge for 50 cars/h, modern aesthetic\nsite planning"
```

The anchoring matters. Without it, a generic capability word like
*"loads"* embeds the same way for a bridge as for a drone, and the
cosine search returns aerospace skills with high confidence. With
the prompt prepended, the same capability is steered toward the
project domain. The anchored string is sent through the same
`text-embedding-3-small` endpoint to produce the **query vector**
$q \in \mathbb{R}^{1536}$.

## C.3 Atlas `$vectorSearch` (MongoDB role #1)

The query vector is handed to MongoDB through the `$vectorSearch`
aggregation stage:

```python
db.skills.aggregate([{
    "$vectorSearch": {
        "index": "skills_embedding_vector",
        "path": "embedding",
        "queryVector": q,
        "numCandidates": 100,
        "limit": 8,
    }
}])
```

Atlas walks its HNSW graph, computes cosine similarity between $q$
and the indexed skill embeddings, and returns the top 8 skills
sorted by similarity, with the score projected back as
`vectorSearchScore`. **We never compute that cosine in Python.**
That is the actual RAG-retrieval moment: *embed the query, ask
MongoDB which catalogued embeddings are closest.*

## C.4 A second exact cosine in Python — and why

There is a second cosine computation, but it is not redundant.
Atlas's `vectorSearchScore` is a ranking-time quantity produced by
an approximate-nearest-neighbour index; it is fine for ordering but
not directly comparable across queries (the same absolute value can
mean different things depending on the local density of the HNSW
graph at the query point). For coalition formation we need a
number that is **comparable across queries** and that we can
threshold. So `_candidates_for()` in
[`src/pipeline/execution.py`](../src/pipeline/execution.py)
re-loads each candidate's full-precision embedding from MongoDB
and computes the exact cosine in NumPy:

$$
\text{coverage}(s, q) \;=\; \frac{q \cdot e_s}{\lVert q \rVert \, \lVert e_s \rVert}
$$

That `coverage` value drives the **0.40 coverage floor** (skills
below it are discarded as off-topic) and feeds the solo value of
each candidate in the coalition formula

$$
v(\{s\}) = 0.6\,\text{coverage} + 0.3\,\text{prior\_rep} + 0.1\,
\frac{\log(1+\text{installs})}{\log(1+\max\,\text{installs})}.
$$

In other words: **Atlas does retrieval; the Python cosine does
admissibility and economics.**

## C.5 Mock mode — a deliberate placeholder

When `USE_MOCK_LLM=true`, the same code path runs but `embed()` is
replaced by a deterministic pseudo-embedding in
[`src/llm/mock.py`](../src/llm/mock.py): each input text is hashed
with SHA-256, the digest seeds a NumPy Mersenne-Twister generator,
and that draws a 1536-dimensional unit vector. The math downstream
still type-checks — cosine is well-defined on any pair of unit
vectors — but the **geometry is meaningless**: similar input
strings do not map to similar vectors.

Mock mode is for plumbing tests and offline demos, not for retrieval
quality. This is why the pipeline also carries a *prompt-domain tag
allow-list* as a second gate (see Section D below): the cosine
signal is trustworthy in real mode and noise in mock mode, so the
tag filter guarantees the candidate set is in-domain regardless of
which `embed()` is in use.

---

# Section D — Coverage floor + domain filter

After Atlas returns its top 8 (per capability, deduplicated across
capabilities → ~15 candidates), two cheap defensive filters run in
Python:

1. **Domain tag allow-list.** Detect the project domain
   (`bridge` / `aircraft` / `rover` / …) by keyword-matching the
   prompt, then drop any skill whose `tags` don't intersect the
   in-domain set for that domain. A small set of domain-agnostic
   skills (`technical-writing`, `applied-mathematics`,
   `project-management`, `regulatory-compliance`, …) pass through
   unconditionally.
2. **Coverage floor.** Drop any remaining candidate whose exact
   NumPy cosine to $q$ is below `0.40`. If the floor wipes out the
   set entirely (rare; mock mode or off-domain prompts), fall back
   to the in-domain catalog scan so the pipeline still produces a
   team instead of crashing.

These two gates together are what keep e.g. `propulsion-systems`
from sneaking onto a bridge subtask purely because its description
mentions "loads" or "dynamics".

---

# Section E — Coalition formation (Shapley-style team selection)

Surviving candidates feed a **greedy combinatorial team-selection**
step that is the actual "magic" of the pipeline.

## E.1 The value function

Each candidate skill $s$ has a **solo value**:

$$
a_s = \alpha \cdot \text{coverage}(s,q) \;+\; \beta \cdot \text{prior\_rep}(s) \;+\; \gamma \cdot \frac{\log(1+\text{installs}(s))}{\log(1+\max\,\text{installs})}
$$

with $\alpha=0.6,\ \beta=0.3,\ \gamma=0.1$. The third term is
pre-normalised by the candidate set's max log-installs so its
contribution is bounded in $[0,1]$.

The **team value** of a set $S$ adds a pairwise complementarity
edge weight on top of the solo sum:

$$
v(S) \;=\; \sum_{i \in S} a_i \;+\; \sum_{i<j,\,i,j\in S} \lambda \cdot (1 - \cos(e_i, e_j))
$$

with $\lambda = 0.4$. Two skills whose embeddings are far apart in
direction (low cosine, high $1-\cos$) reinforce each other; two
near-duplicates barely add anything beyond their solo terms.

This is exactly an **induced-subgraph cooperative game**
(Deng–Papadimitriou 1994) — vertices are skills, edge weights are
$w_{ij} = \lambda \cdot (1 - \cos(e_i, e_j))$, vertex weights are
$a_i$.

## E.2 The greedy build

Capped at $|S| \le 3$:

1. Seed with $\arg\max_s a_s$.
2. While $|S| < 3$: add the candidate with the largest **marginal
   contribution** $\Delta v = v(S \cup \{c\}) - v(S)$. Stop early
   if the best marginal falls below $\tau = 0.05$.

Every step's seed solo and marginal land in the assignment row's
`selection_rationale` so the UI can show *why* a team looks the way
it does.

Code: [`src/agents/coalitions.py`](../src/agents/coalitions.py).

---

# Section F — Set-cover: skills → agents

Once the coalition $S$ of ≤ 3 skills is fixed, we still need
concrete **agents** to actually run the subtask. That's a classic
weighted set-cover:

> Pick ≤ 3 agents from the roster whose `skill_ids` collectively
> cover all of $S$, minimising team size and preferring polyvalent,
> reputable agents.

The greedy `ln |S|` approximation runs in
[`src/agents/set_cover.py`](../src/agents/set_cover.py). At each
step we score every candidate agent by

$$
\text{score}(a) = (\text{still-uncovered skills owned by } a) \cdot (1 + 0.05\,\text{polyvalence}(a)) \cdot \text{reputation}(a)
$$

and pick the highest scorer. The synthetic `agent_marshal` is
deliberately excluded so we never collapse to "marshal does
everything" — the marshal is a fallback, not a competitor.

The full-coverage invariant from Section A.2 guarantees this step
always succeeds: every skill is held by at least one real agent.

---

# Section G — Credit attribution (closed-form Shapley)

Every member of $S$ deserves a fair share of the team's joint
output. Because the value function is an induced-subgraph game,
the **exact Shapley value** has a closed form (Deng–Papadimitriou):

$$
\varphi_i \;=\; a_i \;+\; \tfrac{1}{2}\sum_{j\neq i} w_{ij}.
$$

It costs $O(k^2)$ for $k \le 3$ — essentially free. The Teams tab
shows two derived columns:

- **`shapley`** — $\varphi_i$ rounded to 2 dp.
- **`contribution %`** — the *normalised* Shapley share
  $\varphi_i \,/\, \sum_j \varphi_j \times 100\%$.

A 1-agent team always has `contribution % = 100 %` trivially —
that's not a bug, it's what "fair share" means with one player.
See [GAME_THEORY_PRIMER.md](GAME_THEORY_PRIMER.md) for the full
theory and worked examples.

---

# Section H — What happens after the team is formed

The remaining steps (7 and 9 of the diagram) are out of scope for
this pipeline-walkthrough but linked here for completeness:

- **Step 7. Communication forum** — three rounds of marshal +
  agent messages, persisted to `coalition_messages`. Each subtask
  ends with a 200-token marshal `summary` written to
  `subtask_outputs.summary`. See
  [ARCHITECTURE.md](ARCHITECTURE.md) §"Communication forum".
- **Step 9. Reputation update** — base $\pm$ by validation
  outcome, scaled by `load_factor` and `quality_factor`. Persisted
  on `agents.reputation` so the *next* run sees an updated
  marketplace. See [ARCHITECTURE.md](ARCHITECTURE.md) §"Reputation".

---

## Why the cosine match alone isn't enough

If we *only* used Atlas Vector Search and took the top-3 by cosine
similarity, we'd hit two failure modes:

1. **Near-duplicates.** Three near-identical skills score identical
   cosines and we'd pick three carbon copies of the same expert.
   Useless.
2. **Off-topic skills with strong priors.** A skill with mediocre
   semantic match but high `prior_reputation` and high
   `weekly_installs` would never win on cosine alone — but if we
   *do* let priors in the ranking, an off-topic skill can sneak in
   (this actually happened in the demo before the coverage floor
   was added — `propulsion-systems` was getting picked for a bridge
   subtask).

So the pipeline is **two filters and a graph game**:

- **Filter A — semantic relevance** (Atlas Vector Search +
  in-domain tag allow-list + the 0.40 coverage floor) keeps only
  skills that are *genuinely on-topic*.
- **Filter B — value function** (`v(S) = Σ aᵢ + Σ wᵢⱼ`) prefers
  skills that *complement* each other rather than overlap.
- **Closed-form Shapley** then attributes the team's joint output
  back to each member fairly, for credit and reputation.

The math is from 1994, but it is *exactly* the right math for
"team of agents whose value depends on pairwise interactions",
which is the hackathon prompt's whole premise.

---

## What does each piece *cost*?

| Step | Cost (latency) | Cost ($) | Why |
| --- | --- | --- | --- |
| 1. Decomposer | 1 LLM call | ~$0.01 | gpt-4o on the prompt |
| 2. Embed | 1 OpenAI call per *unique* capability | ~$0.0001 each | text-embedding-3-small, cached |
| 3. Vector search | 1 Atlas aggregation | ≈ free | server-side ANN |
| 4. Coverage floor + tag filter | local | free | list comprehensions |
| 5. Greedy coalition | local | free | $O(k^2)$ for $k \le 3$ |
| 6. Set-cover | local | free | greedy $O(\lvert\text{skills}\rvert\cdot\lvert\text{agents}\rvert)$ |
| 7. Communication forum | 4 LLM calls per subtask | ~$0.04 / subtask | 1 marshal + 3 agents per round |
| 8. Shapley | local | free | $O(k^2)$, $k \le 3$ |
| 9. Reputation | 1 Mongo update per agent | ≈ free | `$inc` + `$set` |

**The dominant cost is step 7 (the LLM communication forum). Every
other step is essentially free.** That's why the demo finishes in
~5 s in mock mode and ~30 s in real-LLM mode — *the math is not
the bottleneck*.

---

## Is this RAG?

Short answer: **step 3 alone is RAG-shaped. The whole pipeline is
not.** It's vector retrieval used as one ingredient in a larger
team-formation algorithm.

**What RAG strictly is.** Retrieval-Augmented Generation has a
canonical shape:

> embed query → vector-search a knowledge base → stuff the top-k
> chunks into an LLM prompt → LLM generates an answer grounded in
> the retrieved text.

The defining move is *"retrieved documents become context for an
LLM call."*

**What we actually do.** Steps 2–3 are literally the retrieval
half of RAG — embed the requirement, query Atlas Vector Search on
`skills.embedding`, take the top-k by cosine. That part is
RAG-shaped.

But steps 4–9 are **not** RAG:

- The retrieved skills are **never stuffed into a prompt.** They
  feed a value function $v(S) = \sum_i a_i + \sum_{i<j} w_{ij}$
  and a greedy coalition algorithm (Deng–Papadimitriou
  induced-subgraph game).
- The "answer" is **not generated by an LLM looking at the
  retrieved docs.** It is computed by a set-cover algorithm
  picking ≤ 3 agents whose `skill_ids` cover the chosen skill set.
- The LLM only re-enters at step 7, where it talks to *agents*,
  not to retrieved skill descriptions. The catalog itself is
  invisible to the LLM.

**So what is it, properly?** Vector retrieval is being used as the
*relevance signal in a combinatorial optimisation problem*, not as
context for generation. More accurate labels:

- "Semantic matching + coalition formation"
- "Vector-search-driven team assembly"
- in academic terms: an *induced-subgraph cooperative game where
  edge weights come from embedding similarity*.

**For the pitch.** If a judge asks *"is this just RAG?"*:

> RAG is one ingredient — Atlas Vector Search gives us the
> semantic relevance signal. But unlike RAG we don't feed the
> retrieved documents to an LLM as context; we feed them into a
> Shapley-style value function that picks a *team* by maximising
> pairwise complementarity. The LLM never sees the skill catalog.
> The Deng–Papadimitriou 1994 math is what's doing the team
> selection; vector search just decides which skills are eligible.

That framing matters because RAG over a 70-row catalog would be
unimpressive — the coalition game on top is what justifies the
architecture.

---

# Appendix — Future direction: ingesting the skills.sh marketplace

The current 70-skill catalog is hand-curated. A natural next step
is to ingest skills from **skills.sh** — Vercel's public open
agent-skills marketplace (~91 k skills as of 2026-05) — so the
catalog reflects what real-world agent runtimes are actually
adopting. This appendix is the research note from a 2026-05-02
spike; no production code was written.

## What skills.sh is

- Web UI: <https://skills.sh/>
- API (public, but auth posture unclear): `https://skills.sh/api/v1/skills`
- CLI: `npx skills` (skill discovery / install from the terminal)
- Each skill's source of truth is a **GitHub repo** containing a
  `SKILL.md` file with YAML frontmatter + markdown body.

A skills.sh API document looks like:

```json
{
  "id":          "vercel-labs/agent-skills/next-js-development",
  "name":        "Next.js Development",
  "description": "React and Next.js performance optimization guidelines…",
  "source":      "vercel-labs/agent-skills",
  "installs":    24531,
  "sourceType":  "github",
  "installUrl":  "https://github.com/vercel-labs/agent-skills",
  "url":         "https://skills.sh/vercel-labs/agent-skills/next-js-development"
}
```

## Field mapping to our catalog

| skills.sh field | Our `skills_seed.json` field | Mapping | Notes |
|---|---|---|---|
| `name` | `name` | direct ✅ | trivial |
| `description` | `description` | direct ✅ | API gives the short summary; `SKILL.md` body has the full text |
| `source` | `repo_url` | derive ✅ | prefix with `https://github.com/` |
| `id` | `skill_id` | normalise ✅ | slug it |
| `installs` | `weekly_installs` | ⚠ **divergent** | skills.sh is **cumulative**; our Shapley solo term `0.1·log(1+installs)/max` expects a recency signal. Either rename our field or compute a weekly delta. |
| — | `tags[]` | ❌ missing | recover from `SKILL.md` frontmatter (Phase 2) or infer via cosine over existing tag embeddings |
| — | `category` | ❌ missing | derive in Phase 2 |
| — | `embedding` (1536-d) | re-compute | re-embed `name + description` with `text-embedding-3-small` at ingest |
| — | `prior_reputation` | ❌ missing | initialise to a clamped function of `log(installs)` |

## Phased pickup plan

1. **Phase 1 — Direct API import.** New
   `src/data/skills_sh_loader.py` with paginated GET against
   `/api/v1/skills` and a `to_seed_record()` that field-maps per
   the table above. Re-run the seed script so each new record gets
   re-embedded with `text-embedding-3-small`.
2. **Phase 2 — Recover `tags` / `category` from `SKILL.md`.** GET
   raw `SKILL.md` from GitHub, parse YAML frontmatter, infer
   missing tags by cosine-matching against the existing curated
   tag embeddings.
3. **Phase 3 — `github_stars` enrichment.** Per `<owner>/<repo>`
   call `GET https://api.github.com/repos/<owner>/<repo>` (auth
   with `GITHUB_TOKEN` for 5 000 req/h). Cache in a
   `skills_sh_cache` collection.

## Risks / watch-outs

- **Schema stability** — skills.sh's API is young; no published
  SLA. Pin fetched JSON snapshots into `data/skills_sh_snapshots/`
  for replay determinism.
- **Cumulative vs. weekly installs** — biggest semantic mismatch;
  blocks the formula change. Must be resolved before Phase 1
  lands.
- **Auth posture** — a 2026-05-02 spot check of
  `curl https://skills.sh/api/v1/skills?per_page=1` returned **HTTP
  401**. Confirm the auth requirement before committing to the
  JSON-API path; if the API really is keyed-only, falling back to
  cloning the source GitHub orgs and parsing `SKILL.md` files
  directly is the recommended primary path.
- **Licensing** — every skill has its own GitHub licence. Surface
  the licence + source link in the UI; don't silently re-publish.
- **MongoDB index rebuild** — re-seeding 150 skills will trigger an
  HNSW rebuild for `skills_embedding_vector`. Plan ~1–2 min
  downtime; do this on a feature branch + scratch DB first.

The `find-skills` skill from skills.sh is **not** a connector — it
is a human-facing discovery assistant that returns LLM prose, not
structured records. Skip it; use the JSON API or the GitHub repos
directly.

---

## Where to read more

- [GAME_THEORY_PRIMER.md](GAME_THEORY_PRIMER.md) — the full theory
  behind sections E + G (induced-subgraph games, Shapley closed
  form, normalised Shapley vs solo value, what each UI column is).
- [TEAMS_TAB.md](TEAMS_TAB.md) — what the user sees in the Teams
  tab (column-by-column).
- [ARCHITECTURE.md](ARCHITECTURE.md) — the broader 9-stage
  orchestrator flow, mock-vs-real plumbing, replay, and indexes.
- [MVP_DESIGN.md](MVP_DESIGN.md) — the original spec, including
  the hackathon prompt mapping ("convey skills / identify peers /
  share context / collaborate").

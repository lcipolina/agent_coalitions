# The matching pipeline — from a free-text requirement to a working team

> *"How does this thing actually pick a team?"*

This is the elevator-pitch view of the system. Every other doc in
`docs/` zooms in on one piece; this one shows the whole flow on a
single page so you (or a judge) can read it in 90 seconds.

---

## TL;DR — one sentence

> A free-text **requirement** is embedded with OpenAI, sent to a
> **MongoDB Atlas Vector Search** index of skills (1536-dim cosine),
> the top semantic matches are filtered through a **coverage floor**
> and a **greedy coalition step** that maximises a Shapley-style
> value function, then a **set-cover step** picks ≤ 3 concrete
> agents that own those skills. MongoDB plays *five* distinct roles
> across that pipeline.

---

## The big picture

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                      USER PROMPT (free text)                           │
   │   "design a bridge for 50 cars, classic victorian, elegant"            │
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
   │  text-embedding-3-small  ──►  1536-dim float32 vector                 │
   │  Cached per process so repeated capabilities are free.                │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   query vector
                                  ▼
   ┌────────── 3. ATLAS VECTOR SEARCH  (MongoDB role #1) ─────────────────┐
   │  db.skills.aggregate([                                               │
   │    { $vectorSearch: {                                                │
   │        index: "skills_embedding_vector",                             │
   │        path:  "embedding",     // 1536-d, cosine                     │
   │        queryVector: <query>,   // from step 2                        │
   │        numCandidates: 50, limit: 8                                   │
   │    }}                                                                │
   │  ])                                                                  │
   │  → returns the 8 skills whose embeddings are closest to              │
   │    the requirement, sorted by cosine similarity.                     │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │   candidate skills (~15 after dedup)
                                  ▼
   ┌────────────────── 4. COVERAGE FLOOR (defensive filter) ───────────────┐
   │  drop any candidate whose cosine ≤ 0.30                               │
   │  → "must be at least loosely on-topic" before priors get a vote.      │
   │  Prevents off-domain skills with high reputation/installs slipping   │
   │  onto the team (e.g. `propulsion-systems` for a bridge subtask).      │
   └──────────────────────────────┬─────────────────────────────────────────┘
                                  │
                                  ▼
   ┌──────── 5. GREEDY COALITION  (Shapley-style team formation) ──────────┐
   │  For each candidate skill s:                                          │
   │    aᵢ  =  v({s})  =  0.6·coverage  +  0.3·prior_rep                  │
   │                       +  0.1·log(1+installs)/max_log_installs        │
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
   │  This is an **induced-subgraph game**                                 │
   │  (Deng–Papadimitriou 1994). For free we get a closed-form             │
   │  Shapley value:    φᵢ  =  aᵢ  +  ½·Σⱼ wᵢⱼ                             │
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
                                  │   3-agent team
                                  ▼
   ┌────────── 7. BLACKBOARD COLLAB  (MongoDB role #3: message bus) ───────┐
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
   │    `contribution %` (a.k.a. normalised Shapley / share of credit;     │
   │    NOT the same as a marginal contribution v(S∪{i})−v(S)).            │
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
| **3. Message bus** | `coalition_messages` | Append-only blackboard, indexed `(run_id, subtask_id, ts)` | Step 7 |
| **4. Persistent memory** | `agents.reputation`, `reputation_updates` | Per-run delta + running reputation across all runs | Step 9 |
| **5. Assignment ledger** | `assignments`, `subtasks`, `subtask_outputs`, `runs` | Every team formed, every output, every cost — the replay surface | Steps 5–9 |

Removing MongoDB removes **five** capabilities, not one. That is the
point.

---

## Why the cosine match alone isn't enough

If we *only* used Atlas Vector Search and took the top-3 by cosine
similarity, we'd hit two failure modes:

1. **Near-duplicates.** Three near-identical skills score identical
   cosines and we'd pick three carbon copies of the same expert.
   Useless.
2. **Off-topic skills with strong priors.** A skill with mediocre
   semantic match but a high `prior_reputation` and high
   `weekly_installs` would never be picked over a perfectly-on-topic
   skill if we only sorted by cosine — but if we *do* let priors in
   the ranking, an off-topic skill can sneak in (this actually
   happened in the demo before the coverage floor was added —
   `propulsion-systems` was getting picked for a bridge subtask).

So the pipeline is **two filters and a graph game**:

- **Filter A — semantic relevance** (Atlas Vector Search + the 0.30
  coverage floor) keeps only skills that are *genuinely on-topic*.
- **Filter B — value function** (`v(S) = Σ aᵢ + Σ wᵢⱼ`) prefers
  skills that *complement* each other rather than overlap.
- **Closed-form Shapley** then attributes the team's joint output
  back to each member fairly, for credit and reputation.

This is the part the user usually thinks of as *"the magic"*. It is
maths from 1994 (Deng–Papadimitriou), but it is *exactly* the right
maths for *"team of agents whose value depends on pairwise
interactions"*, which is the hackathon prompt's whole premise.

---

## What does each piece *cost*?

| Step | Cost (latency) | Cost ($) | Why |
| --- | --- | --- | --- |
| 1. Decomposer | 1 LLM call | ~$0.01 | gpt-4o on the prompt |
| 2. Embed | 1 OpenAI call per *unique* capability | ~$0.0001 each | text-embedding-3-small, cached |
| 3. Vector search | 1 Atlas aggregation | ≈ free | server-side ANN |
| 4. Coverage floor | local | free | a list comprehension |
| 5. Greedy coalition | local | free | O(k²) for k ≤ 3 |
| 6. Set-cover | local | free | greedy O(\|skills\|·\|agents\|) |
| 7. Blackboard collab | 4 LLM calls per subtask | ~$0.04 / subtask | 1 marshal + 3 agents per round |
| 8. Shapley | local | free | O(k²), k ≤ 3 |
| 9. Reputation | 1 Mongo update per agent | ≈ free | $inc + $set |

The dominant cost is step 7 (the LLM blackboard). Everything else is
essentially free. **The math is not the bottleneck.** That's why the
demo pipeline finishes in ~5 s in mock mode and ~30 s in real-LLM
mode.

---

## How the embeddings (and the cosine) are actually produced

The vector-search layer is the most important step of the pipeline
to get right, and it's the one most often hand-waved in agent-system
papers, so this section spells out the full chain.

### Which embedding model, and where does it run?

We do **not** use a local embedding library (Sentence-Transformers,
HuggingFace `transformers`, FastEmbed). We use a *hosted* embedding
model: **OpenAI's `text-embedding-3-small`**, accessed over HTTPS
through the official `openai` Python SDK. OpenAI publishes two
distinct families of models on the same API — chat models such as
`gpt-4o-mini` (autoregressive decoders that emit text) and embedding
models such as `text-embedding-3-small` (transformer encoders that
emit a fixed-size vector). We use both: chat models for the
decomposer, the marshals, the agents, and the synthesiser; the
embedding model only for the retrieval layer described below. The
embedding endpoint returns 1536 float-32 values per input string;
nothing about the model weights ever runs locally. The reason for
picking the hosted model over an open-source one is empirical: the
skill marketplace contains short, technical phrases like *"cable-stayed
bridge systems"* and *"aerodynamics and CFD"*, and OpenAI's third-generation
embeddings give noticeably cleaner cosine separation between domains
than the small open-source models commonly used in tutorials. The
trade-off is a network call per query and a small per-token cost,
both of which are negligible at the scale of a single hackathon
demo (≈ 70 catalogue embeddings + a handful of query embeddings per
run, well under one cent in total).

### Are the catalogue embeddings stored already-vectorised in MongoDB?

Yes. This is the key architectural decision. Each document in the
`skills` collection is shaped like:

```json
{
  "skill_id": "cable-stayed-bridge-systems",
  "name": "Cable-Stayed Bridge Systems",
  "description": "Design and analysis of cable-stayed bridges …",
  "tags": ["cable-stayed", "bridge", "civil"],
  "prior_reputation": 0.86,
  "weekly_installs": 7400,
  "embedding": [0.0123, -0.0451, 0.0089, …]   // 1536 floats, persisted
}
```

The `embedding` field is computed **once**, at seeding time, by the
seed script (`python -m src.scripts.seed_skills`), and written
straight into the document. The catalogue is therefore "vectorised
at rest": after seeding, the marketplace lives in MongoDB as a set
of pre-computed 1536-dimensional points, and Atlas builds a cosine
HNSW index on top of that field. At query time we never re-embed
the catalogue; only the query vector is fresh. This matters for
three reasons. First, retrieval becomes a pure server-side
aggregation — no LLM in the loop, no model inference on the
catalogue side, latency in the millisecond range. Second, the
pipeline is replayable: a fixed catalogue plus a fixed query
deterministically returns the same nearest neighbours every time.
Third, the system stays cheap: embedding the catalogue costs roughly
$0.0001 *in total* once, and each subsequent run only pays for the
handful of query embeddings it actually issues. The standing
constraint is that query and catalogue vectors must be produced by
the *same* model — cosine across embedding spaces is meaningless —
so the codebase pins `text-embedding-3-small` everywhere; changing
the model would require re-seeding the catalogue.

### Indexing time (one-shot, when the catalog is seeded)

The catalog lives in `data/skills_seed.json` (70 skills as of this
writing). When the seed script runs, every skill is converted to a
single short document — its `name`, `description`, and `tags` joined
into a paragraph — and that paragraph is sent to OpenAI's embedding
endpoint via the official **`openai` Python SDK**
(`OpenAI().embeddings.create(model=..., input=...)`). The model is
**`text-embedding-3-small`**, which returns a 1536-dimensional
float vector per call. Each skill document is then written to
MongoDB with the embedding stored alongside the rest of its fields,
i.e. `{ skill_id, name, description, tags, prior_reputation,
weekly_installs, embedding: [1536 floats], … }`.

Once the documents are in MongoDB, an **Atlas Vector Search index**
named `skills_embedding_vector` is created over the `skills.embedding`
field. The index is configured with `type: "vectorSearch"`,
`numDimensions: 1536`, `similarity: "cosine"`. Atlas builds an
**HNSW** (Hierarchical Navigable Small World) graph on those vectors
behind the scenes — that's the data structure that makes
sub-millisecond approximate nearest-neighbour lookup possible at
scale. We do not implement HNSW; Atlas does. Code references:
[src/db/seed.py](../src/db/seed.py) for the seeding loop and
[src/db/indexes.py](../src/db/indexes.py) for the index definition.

### Query time (per subtask, in `_candidates_for`)

When a run starts, the LLM decomposer produces a DAG of subtasks,
each carrying a list of free-text **required capabilities** (e.g.
T1 "Site & geometry" might need *"site planning"*, *"geometry"*,
*"alignment"*). For every capability we then build a
**prompt-anchored query string** by concatenating the run's full
prompt with the capability — for example, `"design a 2 km bridge
for 50 cars/h, modern aesthetic\nsite planning"`. The anchoring
step matters: without it, a generic capability word like *"loads"*
embeds the same way for a bridge as for a drone, and the cosine
search returns aerospace skills with high confidence. With the
prompt prepended, the same capability is steered toward the project
domain. The anchored string is sent through the same
`text-embedding-3-small` endpoint to produce the **query vector**
$q \in \mathbb{R}^{1536}$.

The query vector is then handed to MongoDB through the
**`$vectorSearch` aggregation stage**:

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

### A second, exact cosine in Python — and why

There is a second cosine computation, but it is not redundant.
Atlas's `vectorSearchScore` is a ranking-time quantity produced by
an approximate-nearest-neighbour index; it is fine for ordering, but
not directly comparable across queries (the same absolute value can
mean different things depending on the local density of the HNSW
graph at the query point). For the coalition-formation step we need
a number that is **comparable across queries** and that we can
reason about with a fixed threshold. So `_candidates_for()` in
[src/pipeline/execution.py](../src/pipeline/execution.py) re-loads
each candidate skill's full-precision embedding from MongoDB and
computes the exact cosine in NumPy:

$$
\text{coverage}(s, q) \;=\; \frac{q \cdot e_s}{\lVert q \rVert \, \lVert e_s \rVert}
$$

That `coverage` value is what drives the **0.40 coverage floor**
(skills below it are discarded as off-topic) and what feeds into the
solo value of each candidate in the coalition formula
$v(\{s\}) = 0.6\,\text{coverage} + 0.3\,\text{prior\_rep} + 0.1\,
\log(1+\text{installs})$. In other words, Atlas does retrieval; the
Python cosine does *admissibility and economics*.

### Mock mode — a deliberate placeholder

When `USE_MOCK_LLM=true`, the same code path runs but `embed()` is
replaced by a deterministic pseudo-embedding in `src/llm/mock.py`:
each input text is hashed with SHA-256, the digest seeds a NumPy
Mersenne-Twister generator, and that draws a 1536-dimensional unit
vector. The math downstream still type-checks — cosine is
well-defined on any pair of unit vectors — but the **geometry is
meaningless**: similar input strings do not map to similar vectors.
Mock mode is for plumbing tests and offline demos, not for retrieval
quality. This is precisely why the pipeline also carries a
prompt-domain tag allow-list as a second gate: the cosine signal is
trustworthy in real mode and noise in mock mode, so the tag filter
is what guarantees the candidate set is in-domain regardless of
which `embed()` is in use.

### One-line summary for a pitch or a paper abstract

OpenAI's `text-embedding-3-small` model embeds the skill catalog
into 1536-dimensional vectors, which MongoDB Atlas Vector Search
indexes with a cosine-similarity HNSW graph. At query time we
prompt-anchor each subtask capability, embed it through the same
model, and ask Atlas to return the nearest skills. We then re-score
the candidates with an exact NumPy cosine so the same number can
gate admission (the 0.40 coverage floor) and feed the coalition
value function — turning vector retrieval into the relevance signal
of a combinatorial team-formation problem rather than just the
retrieve-then-generate of standard RAG.

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

The defining move is *"retrieved documents become context for an LLM
call."*

**What we actually do.** Steps 2–3 are literally the retrieval half
of RAG — embed the requirement, query Atlas Vector Search on
`skills.embedding`, take the top-k by cosine. That part is
RAG-shaped.

But steps 4–9 are **not** RAG:

- The retrieved skills are **never stuffed into a prompt.** They
  feed a value function $v(S) = \sum_i a_i + \sum_{i<j} w_{ij}$ and a
  greedy coalition algorithm (Deng–Papadimitriou induced-subgraph
  game).
- The "answer" is **not generated by an LLM looking at the retrieved
  docs.** It is computed by a set-cover algorithm picking ≤ 3
  agents whose `skill_ids` cover the chosen skill set.
- The LLM only re-enters at step 7 (the blackboard), where it talks
  to *agents*, not to retrieved skill descriptions. The catalog
  itself is invisible to the LLM.

**So what is it, properly?** Vector retrieval is being used as the
*relevance signal in a combinatorial optimisation problem*, not as
context for generation. More accurate labels:

- "Semantic matching + coalition formation"
- "Vector-search-driven team assembly"
- in academic terms: an *induced-subgraph cooperative game where
  edge weights come from embedding similarity*.

The closest RAG cousin is *"retrieval-augmented decision-making"*
(retrieval feeding a non-LLM decision procedure), but that's a
stretch. The honest summary is: **we use vector search as a feature,
not as context for an LLM.**

**For the pitch.** If a judge asks *"is this just RAG?"*:

> RAG is one ingredient — Atlas Vector Search gives us the semantic
> relevance signal. But unlike RAG we don't feed the retrieved
> documents to an LLM as context; we feed them into a Shapley-style
> value function that picks a *team* by maximising pairwise
> complementarity. The LLM never sees the skill catalog. The
> Deng–Papadimitriou 1994 math is what's doing the team selection;
> vector search just decides which skills are eligible.

That framing matters because RAG over a 70-row catalog would be
unimpressive — the coalition game on top is what justifies the
architecture.

---

## Where to read more

- [GAME_THEORY_PRIMER.md](GAME_THEORY_PRIMER.md) — the full theory
  behind step 5 + step 8 (induced-subgraph games, Shapley closed
  form, normalised Shapley vs solo value, what each UI column is).
- [TEAMS_TAB.md](TEAMS_TAB.md) — what the user sees in the Teams tab
  (column-by-column).
- [SKILL_SEEDING.md](SKILL_SEEDING.md) — how the 70-skill catalog
  gets generated and how every skill is guaranteed to be held by at
  least one agent.
- [ARCHITECTURE.md](ARCHITECTURE.md) — the broader 9-stage
  orchestrator flow, mock-vs-real plumbing, replay, and indexes.
- [MVP_DESIGN.md](MVP_DESIGN.md) — the original spec, including the
  hackathon prompt mapping ("convey skills / identify peers / share
  context / collaborate").

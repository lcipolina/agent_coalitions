# The "Teams" tab — what each box and column means

This document walks through every piece of the **Teams** tab in the
Streamlit UI and explains where the numbers come from, so you can
decide what to fix or simplify.

The tab is rendered by [`app.py`](../app.py) (search for
`with tab_coal:`) and reads from the `assignments`, `subtasks` and
`skills` collections in MongoDB.

---

## 1. The page caption

```
One team is formed per subtask (T1, T2, …). The orchestrator picks
skills via Atlas Vector Search on each subtask's required
capabilities, then a set-cover step assigns concrete agents.
```

This is the mental model:

```
Prompt
  │
  ▼  (LLM decomposer)
Subtasks T1, T2, … Tn   ← each carries `required_capabilities` (free-text)
  │
  ▼  (Atlas Vector Search per subtask)
Skills picked from data/skills_seed.json   ← e.g. "composite-materials"
  │
  ▼  (greedy weighted set-cover, src/agents/set_cover.py)
Agents assigned to the team   ← real Mongo agent docs
```

One subtask → one team. The Teams tab is a list of these teams, one
**collapsible box per subtask**.

---

## 2. The expander header

```
**T3 — Material selection**  ·  agents: #017 — composites, layup, #004 — load, hydrology
```

Three pieces of information:

- **`T3`** — the subtask id. Stable across the run; used as a foreign
  key in every other tab.
- **`Material selection`** — the subtask `title`, written by the LLM
  decomposer (or by the deterministic mock decomposer in mock mode).
- **`agents: …`** — the friendly labels of the agents on this team.
  Each label is built by `_agent_label()` in `app.py`:
  `"#NNN — {top 3 skill keywords}"`. The raw `agent_id` is in Mongo
  but never shown here.

---

## 3. The "Skills selected" table

This is the **first table inside the expander**. It is the team's
*toolbox* — the skills the marshal decided this subtask needs.

| column            | source                                                                 | meaning                                                                                          |
| ----------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `skill_id`        | `skills` collection                                                    | Catalogue id, e.g. `composite-materials`. Stable identifier.                                     |
| `name`            | `skills` collection                                                    | Human-readable name from `data/skills_seed.json`.                                                |
| `category`        | `skills` collection                                                    | One of `engineering` / `software` / `design` / `management` / `math`. Useful for quick grouping. |
| `prior_reputation`| `skills` collection                                                    | Skill's standing **in the catalogue**, *not* on this run. Computed once at seed time.            |
| `weekly_installs` | `skills` collection                                                    | Marketplace popularity proxy from the seed JSON. Same value for every run.                       |
| `assigned_to`     | per-team mapping built from `assignments.contribution_scores`          | Which agent on **this** team carries this skill. `—` means no agent on the team had it.          |

**Row order**: the order in which the marshal picked the skills (the
top-ranked one is first).

> **Important**: `prior_reputation` and `weekly_installs` describe the
> **skill itself**, not the team. They don't change between teams or
> between runs. They are shown so you can see *why* a skill was a
> plausible pick — high prior_reputation skills are preferred when
> Vector Search ties.

---

## 4. The "Agent contributions" table

This is the **second table inside the expander**. It is the team's
*roster with credit assignment*.

| column                | source                                | meaning                                                                                                                                                       |
| --------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent`               | `_agent_label(agent_id)`              | Friendly label of the agent.                                                                                                                                  |
| `score`               | computed by `coalition_value()`       | The agent's **solo Shapley value** for the skills it contributed (see formula below).                                                                         |
| `skills_contributed`  | computed in set-cover                 | Comma-separated list of skill_ids the agent actually covered for this team. May be a strict subset of the agent's full skill list.                            |

The **score** formula (printed below the tables in the UI):

```
v({s}) = 0.6·coverage(s, query)        ← how well the skill matches the subtask's vector
       + 0.3·prior_reputation(s)       ← the catalogue prior
       + 0.1·log(1 + installs(s)) / max_log_installs
```

> **Naming honesty.** This is **not** the Shapley value. It is the
> *characteristic function* `v(S)` evaluated on a single-skill
> coalition `S = {s}` — sometimes called the "solo value". For a
> singleton it happens to equal the Shapley value of `s` because
> there's nothing to average over.
>
> The classic Shapley value is the *average marginal contribution* of
> a player over **all** orderings:
>
> ```
> φ_i(v) = Σ_{S ⊆ N\{i}}  (|S|!·(n-|S|-1)! / n!) · [v(S∪{i}) − v(S)]
> ```
>
> The code in `src/agents/coalitions.py` never enumerates all
> orderings. What it *does* do during team growth is pick the
> candidate with the largest **single marginal contribution**
> `v(S ∪ {c}) − v(S)` — i.e. one term of the Shapley sum. The
> docstring on `coalition_value()` calls this a
> **"rank-1 Shapley approximation"**, which is the accurate framing.

When an agent covers multiple skills its score is the **sum of the
solo values of those skills**. So:

- An agent with a single very-relevant skill can score higher than
  one with three weakly-relevant skills.
- A solo team **does not** automatically score 100% — the score
  reflects the relevance of each skill to the subtask query, not the
  share of work.

---

## 5. The rationale caption

Below the two tables:

```
_Rationale:_ <one short paragraph>
```

This is the marshal's natural-language justification for why this
team makes sense for this subtask. It is the **only** LLM-generated
field on the page (real-LLM mode); in mock mode it comes from a
deterministic role-keyed router in `src/llm/mock.py`.

---

## 6. The footnote at the bottom of the tab

```
**About the `score` column.** It is the *solo Shapley value* of the
skill the agent contributed …
```

This is just the formula above, restated for the audience that
scrolled past all the expanders.

---

## Common confusions and what would fix them

These are honest weak spots — not bugs, just UI choices that may not
match your intuition:

1. **`prior_reputation` and `weekly_installs` look static across teams.**
   They are. They live on the *skill*, not on the assignment. If you
   want them to feel "live", we could remove them from the per-team
   table and show them once in a separate tab, or replace them with a
   per-run figure (e.g. how many teams in this run picked the skill).

2. **`assigned_to = —`** *should no longer happen* after the seeding
   fix in [`SKILL_SEEDING.md`](SKILL_SEEDING.md), because every skill
   is now held by at least one agent. If you still see `—`, please
   send a screenshot — that is a real bug.

3. **The same skill can appear in two different teams.** This is by
   design (the caption says so) and reflects the fact that two
   subtasks may share required capabilities. If it feels wrong, the
   fix is in the marshal step, not here.

4. **The roster table mixes "score" (a Shapley number) and
   "skills_contributed" (a comma-separated list).** This may read as
   apples-and-oranges. We could split it into two columns with
   per-skill scores, or aggregate to one number per agent. Up to you.

5. **There's no "team total" row.** The aggregate Shapley value (sum
   of agent scores) is computed but not shown. We could surface it as
   a small badge in the expander header.

Tell me which of these you'd like changed and I'll implement.

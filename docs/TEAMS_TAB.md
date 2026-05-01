# The "Teams" tab — what each box and column means

This document walks through every piece of the **Teams** tab in the
Streamlit UI and explains where the numbers come from, so you can
decide what to fix or simplify.

The tab is rendered by [`app.py`](../app.py) (search for
`with tab_coal:`) and reads from the `assignments`, `subtasks` and
`skills` collections in MongoDB.

> **For the *how does this whole thing work?* view**, see
> [MATCHING_PIPELINE.md](MATCHING_PIPELINE.md) — it shows the
> `requirement → vector search → coalition → set-cover → Shapley`
> flow on one page with infographics.

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
**T3 — Material selection**  ·  agents: #017, #004, #009
```

Three pieces of information:

- **`T3`** — the subtask id. Stable across the run; used as a foreign
  key in every other tab.
- **`Material selection`** — the subtask `title`, written by the LLM
  decomposer (or by the deterministic mock decomposer in mock mode).
- **`agents: …`** — the short labels of the agents on this team. Each
  label is just `"#NNN"` (the numeric suffix of the persistent
  `agent_id`). The label deliberately does **not** include the
  agent's owned skills, because the *skills the agent actually
  contributes for this subtask* are listed in the `skills_contributed`
  column of the contributions table below — showing them in the label
  too would be redundant and misleading whenever an agent's broader
  skill set overlaps domains it isn't currently working in.

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

| column                | source                                  | meaning                                                                                                                                                                                                                |
| --------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent`               | `_agent_label(agent_id)`                | Short label of the agent (e.g. `#017`).                                                                                                                                                                                |
| `shapley`             | `shapley_values()` in `coalitions.py`   | The agent's **exact Shapley value** for this team — the closed-form payoff `φᵢ = aᵢ + ½·Σ wᵢⱼ` for the induced-subgraph game, summed over the skills the agent contributed. By the *efficiency* axiom this column sums to `v(N)`. |
| `share %`             | `100 · shapley / Σ shapley`             | Same number, normalised to 100 % across the team. Reads as "fraction of this team's joint output fairly attributable to this agent". This is the **standardised / normalised Shapley value** — what people often call the "share of credit". |
| `skills_contributed`  | computed in set-cover                   | Comma-separated list of skill_ids the agent actually covered for this team. May be a strict subset of the agent's full skill list.                                                                                     |

### What is the "solo value" `aᵢ` and where does it come from?

For each skill `s` matched against the subtask query, the orchestrator
computes a **solo value** — the *characteristic function* `v(·)`
evaluated on the singleton coalition `{s}`:

```
aᵢ = v({s}) = 0.6·coverage(s, query)              ← cosine match to the subtask
            + 0.3·prior_reputation(s)             ← the catalogue prior
            + 0.1·log(1 + installs(s)) / max_log_installs
```

This number is **not displayed in the Teams tab**, but it is the
input to two things:

1. The exact Shapley closed form `φᵢ = aᵢ + ½·Σⱼ wᵢⱼ` shown above.
2. The greedy team-formation loop, which seeds with the highest-`aᵢ`
   skill and then adds the candidate with the largest single marginal
   contribution at each step.

It also feeds the **Reputation tab** as `mean_contribution_score` —
the average solo value of the skills an agent contributed across the
run, used as a quality factor in the per-agent reputation delta.

### What is `wᵢⱼ` (the edge weight)?

```
wᵢⱼ = 0.4 · (1 − cos(eᵢ, eⱼ))
```

— the **complementarity bonus** between two skills, measured as
`1 minus the cosine similarity` of their embeddings. Two skills that
point in different directions in embedding space (e.g. `geotechnical`
and `aerodynamics`) cover more of the subtask between them than
either alone, so adding them together earns the team an extra `wᵢⱼ`
on top of `aᵢ + aⱼ`. The Shapley value splits that bonus fairly: half
to each endpoint of the edge.

### So what does `share %` actually tell you?

It is the agent's slice of **the team's joint output `v(N)`** —
solo strengths *plus* the complementarities the agent helps unlock.
A 33% share in a 3-agent team means "roughly equal contributors"; a
60/30/10 split means one agent both has a strong solo value *and*
benefits a lot from complementarities with the other two.

> **Naming.** `share %` and "normalised Shapley value" and "share of
> credit" are three names for the same number: `φᵢ / Σⱼ φⱼ · 100 %`.
> The unnormalised `shapley` column is the raw Shapley payoff in the
> same units as the solo value formula above.

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
**About the `shapley` and `share %` columns.** `shapley` is the
exact Shapley value for the induced-subgraph game …
```

This is just §4 restated for the audience that scrolled past all the
expanders.

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

4. **A 1-agent team has `share % = 100 %` trivially.** The Shapley
   value of a lone player equals `v({s})` (no orderings to average
   over). That's not a bug — it is what "fair share" means when
   there's one player.

5. **There's no "team total" row.** The aggregate Shapley value
   `v(N) = Σ φᵢ` is computed but not shown. We could surface it as a
   small badge in the expander header.

Tell me which of these you'd like changed and I'll implement.

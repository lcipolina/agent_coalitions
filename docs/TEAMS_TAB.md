# The "Teams" tab — what each box and column means

This document walks through every piece of the **Teams** tab in the
Streamlit UI and explains where the numbers come from, so you can
decide what to fix or simplify.

The tab is rendered by [`app.py`](../app.py) (search for
`with tab_coal:`) and reads from the `assignments`, `subtasks` and
`skills` collections in MongoDB.

> **For the *how does this whole thing work?* view**, see
> [MATCHING_PIPELINE.md](MATCHING_PIPELINE.md) — it shows the
> `prompt → vector search → coalition → set-cover → Shapley`
> flow on one page with infographics.

---

## 1. The page caption

```
One team is formed per subtask (T1, T2, …). The orchestrator assigns
skills to each team via cosine similarity between the subtask's
required capabilities and the skill marketplace. Skills can be shared
across teams when capabilities overlap.
```

This is the mental model:

```
Prompt
  │
  ▼  (LLM decomposer)
Subtasks T1, T2, … Tn   ← each carries `required_capabilities` (free-text)
  │
  ▼  (cosine similarity vs. the skill marketplace, via Atlas Vector Search)
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
  `agent_id`), or `Marshal` for the synthetic fallback. The label
  deliberately does **not** include the agent's owned skills, because
  the *skills the agent actually contributes for this subtask* are
  listed in the `skills_contributed` column of the contributions table
  — showing them in the label too would be redundant and misleading
  whenever an agent's broader skill set overlaps domains it isn't
  currently working in.

The expander is **collapsed by default** so the page reads as a list
of team headers; expand the ones you want to inspect.

---

## 3. The "Skills selected from marketplace" table

This is the **first table inside the expander**. It is the team's
*toolbox* — the skills the orchestrator decided this subtask needs.

The caption above the table:

> Each row is one skill this team needs. Skills are picked from the
> marketplace by cosine similarity against the subtask's required
> capabilities; `reputation_score` and `weekly_installs` come from
> the marketplace, and `agent_assigned` shows which team member
> supplies that skill.

| column            | source                                                                 | meaning                                                                                          |
| ----------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `skill_id`        | `skills` collection                                                    | Catalog id, e.g. `composite-materials`. Stable identifier.                                       |
| `category`        | `skills` collection                                                    | One of `engineering` / `software` / `design` / `management` / `math`. Useful for quick grouping. |
| `name`            | `skills` collection                                                    | Human-readable name from `data/skills_seed.json`.                                                |
| `reputation_score`| `skills.prior_reputation`                                              | Skill's standing **in the marketplace**, *not* on this run. Computed once at seed time. Renamed in the UI from `prior_reputation` to read as a marketplace-style "score". |
| `weekly_installs` | `skills` collection                                                    | Marketplace popularity proxy from the seed JSON. Same value for every run.                       |
| `agent_assigned`  | per-team mapping built from `assignments.contribution_scores`          | Which agent on **this** team carries this skill. Renamed in the UI from `assigned_to`.           |

**Row order**: the order in which the orchestrator picked the skills
(seed first, then by greedy marginal). The first row is the seed
skill of the coalition.

> **Important**: `reputation_score` and `weekly_installs` describe the
> **skill itself**, not the team. They don't change between teams or
> between runs. They are shown so you can see *why* a skill was a
> plausible pick — high `reputation_score` skills are preferred when
> cosine similarities tie.

---

## 4. The "Agent contributions" table

This is the **second table inside the expander**. It is the team's
*roster with credit assignment*.

| column                | source                                  | meaning                                                                                                                                                                                                                |
| --------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent`               | `_agent_label(agent_id)`                | Short label of the agent (e.g. `#017`, or `Marshal`).                                                                                                                                                                  |
| `contribution %`      | `100 · shapley / Σ shapley`             | The **normalised Shapley value** — fraction of the team's joint output fairly attributable to this agent. Sums to ~100% across the table by the *efficiency* axiom. Rounded to 1 decimal.                              |
| `skills_contributed`  | computed in set-cover                   | Comma-separated list of skill_ids the agent actually covered for this team. May be a strict subset of the agent's full skill list.                                                                                     |

The raw, unnormalised `shapley` column from the assignment row is
**not** displayed in the tab — game-theory jargon distracts from the
demo, so the percentage view is shown alone. The raw values are still
persisted in `assignments.contribution_scores[*].shapley` if you need
them in the database.

### What is the "solo value" `aᵢ` and where does it come from?

For each skill `s` matched against the subtask query, the orchestrator
computes a **solo value** — the *characteristic function* `v(·)`
evaluated on the singleton coalition `{s}`:

```
aᵢ = v({s}) = 0.6·coverage(s, query)              ← cosine match to the subtask
            + 0.3·prior_reputation(s)             ← the marketplace prior
            + 0.1·log(1 + installs(s)) / max_log_installs
```

This number is **not displayed in the Teams tab**, but it is the
input to two things:

1. The exact Shapley closed form `φᵢ = aᵢ + ½·Σⱼ wᵢⱼ` that drives the
   `contribution %` column.
2. The greedy team-formation loop, which seeds with the highest-`aᵢ`
   skill and then adds the candidate with the largest single marginal
   contribution at each step.

It also feeds the per-agent reputation update as
`mean_contribution_score` — the average solo value of the skills an
agent contributed across the run, used as a quality factor in the
reputation delta.

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

### So what does `contribution %` actually tell you?

It is the agent's slice of **the team's joint output `v(N)`** —
solo strengths *plus* the complementarities the agent helps unlock.
A 33% share in a 3-agent team means "roughly equal contributors"; a
60/30/10 split means one agent both has a strong solo value *and*
benefits a lot from complementarities with the other two.

> **Naming caveat.** *normalised Shapley value*, *share of credit*,
> and `contribution %` are three names for the same number:
> `φᵢ / Σⱼ φⱼ · 100 %`.
>
> ⚠️ This is **not** the same as a *marginal contribution* in the
> game-theory sense, which is `v(S ∪ {i}) − v(S)` — the value an
> agent adds when joining a particular coalition `S`. The Shapley
> value is the *average* of those marginal contributions across all
> orderings; `contribution %` is that Shapley value rescaled to the
> team total. We avoid the term "marginal contribution" in the UI
> precisely because it has a different, narrower meaning in the
> literature.

---

## 5. The rationale caption

Below the two tables:

```
_Rationale:_ Seed: <skill> (solo=0.x). +<skill> (marginal=0.y). …
```

This is the deterministic build trace of the greedy coalition step:
the seed skill and its solo value, followed by each subsequent skill
and its marginal contribution to `v(S)`. It is computed in
`form_coalition()` in [`src/agents/coalitions.py`](../src/agents/coalitions.py)
and persisted as `assignments.selection_rationale`. No LLM is involved.

---

## 6. The footnotes at the bottom of the tab

After all the team boxes, three captions explain the math, in
increasing order of detail:

1. **TL;DR caption.** *"`contribution %` = each agent's fair share
   of the team's joint output, computed via the closed-form Shapley
   value of the induced-subgraph game."*
2. **Naming caption.** Repeats the *normalised Shapley / share of
   credit / not a marginal contribution* warning from §4.
3. **Formula caption.** Spells out
   `φᵢ = aᵢ + ½·Σ wᵢⱼ`,
   with `aᵢ = 0.6·coverage + 0.3·prior_reputation + 0.1·log(1+installs)/max`
   and `wᵢⱼ = 0.4·(1 − cos(eᵢ, eⱼ))`, and notes that by the
   *efficiency* axiom `Σᵢ φᵢ = v(N)`.

These are §§3–4 of this document restated for the audience that
scrolled past all the expanders.

---

## Common confusions and what would fix them

These are honest weak spots — not bugs, just UI choices that may not
match your intuition:

1. **`reputation_score` and `weekly_installs` look static across teams.**
   They are. They live on the *skill*, not on the assignment. If you
   want them to feel "live", we could remove them from the per-team
   table and show them once in a separate tab, or replace them with a
   per-run figure (e.g. how many teams in this run picked the skill).

2. **`agent_assigned = —`** *should no longer happen* after the
   seeding fix described in [`MATCHING_PIPELINE.md` §A.2–A.3](MATCHING_PIPELINE.md#a2-the-full-coverage-invariant),
   because every skill is now held by at least one agent. If you
   still see `—`, that is a real bug.

3. **The same skill can appear in two different teams.** This is by
   design (the page caption says so) and reflects the fact that two
   subtasks may share required capabilities. If it feels wrong, the
   fix is in the skill-selection step, not here.

4. **A 1-agent team has `contribution % = 100 %` trivially.** The
   Shapley value of a lone player equals `v({s})` (no orderings to
   average over). That's not a bug — it is what "fair share" means
   when there's one player.

5. **There's no "team total" row.** The aggregate Shapley value
   `v(N) = Σ φᵢ` is computed but not shown. We could surface it as a
   small badge in the expander header.

6. **The raw `shapley` column is hidden.** Only `contribution %` is
   shown. The raw payoff is still in MongoDB
   (`assignments.contribution_scores[*].shapley`) — surfacing it is a
   one-line change to the `contrib_rows` builder in
   [`app.py`](../app.py).

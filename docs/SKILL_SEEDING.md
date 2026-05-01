# Skill seeding & full-coverage guarantee

This note explains how skills are loaded into MongoDB and how the 20
synthetic agents are populated so that **every skill is held by at
least one agent**. It is referenced from `src/db/seed.py` and from the
hackathon demo notes.

## TL;DR

- The skill catalogue lives in [`data/skills_seed.json`](../data/skills_seed.json) (70 skills today).
- Each skill is upserted into Mongo with its `embedding` (1536-dim, OpenAI `text-embedding-3-small`) and a deterministic `prior_reputation`.
- 20 agents are then synthesised with a **deterministic seeding algorithm** that guarantees full coverage of the catalogue.

---

## Why coverage matters

The pipeline has two related layers:

1. **Marshal** picks the *skills* a team needs (via Atlas Vector Search on the prompt).
2. **Set-cover** ([`src/agents/set_cover.py`](../src/agents/set_cover.py)) picks the *agents* that carry those skills.

If a chosen skill is **not held by any agent**, the set-cover step has
nothing to assign it to. Downstream the *Skills selected* table in the
Teams tab shows `assigned_to = —` and the marshal-fallback agent
silently absorbs the work. That looks broken in a demo, even though
the math is internally consistent.

So we need a hard invariant:

> **Every skill in the catalogue must be carried by at least one agent.**

## The arithmetic constraint

The seeder gives each agent a fixed number of skills. The total
*skill-slots* across all agents must be `>=` the number of skills:

```
sum(AGENT_SKILL_DISTRIBUTION) >= len(skills)
```

The original distribution `[2]*14 + [3]*4 + [4]*2 = 48 slots` is
strictly less than `70 skills`, so coverage was mathematically
impossible — there was no way to assign all 70 skills with only 48
slots.

The current distribution `[3]*10 + [4]*8 + [5]*2 = 72 slots` gives us
`72 - 70 = 2` slack slots: enough to cover everything plus a little
redundancy.

## The seeding algorithm

Implemented in [`src/db/seed.py::seed_agents`](../src/db/seed.py).

```text
1. Sanity check
   - Read all skills from Mongo.
   - If sum(AGENT_SKILL_DISTRIBUTION) < len(skills): RAISE.
     (This is the "if you add more skills than slots, you'll get a
     clear error instead of silent gaps" guard.)

2. Coverage pass (round-robin)
   - Shuffle the skill list (deterministically, using settings.seed).
   - Walk through the skills one by one; for each skill, drop it
     into the next agent that still has a free slot.
   - Move to the next agent (modulo 20) after each placement.
   - Result: after this pass, every skill is held by exactly one
     agent, and the leftover capacity is `total_slots - len(skills)`
     slots distributed across agents.

3. Random-fill pass
   - For any agent that still has free slots, sample additional
     skills from the catalogue (excluding ones it already has).
   - This adds redundancy: a few skills end up with two carriers,
     which the set-cover algorithm exploits when forming small
     teams.
```

Both passes use a `random.Random(settings.seed)` so reseeding from
the same `seed` produces the same agent rosters. Demos are reproducible.

## Why this isn't more complicated than it sounds

It's a 25-line algorithm:

- 1 check (slots vs skills),
- 1 shuffle + 1 round-robin loop (coverage),
- 1 small loop to top up empty slots (redundancy).

The wording in commit messages can make it sound elaborate; the code
itself is short and is fully covered by the existing tests in
`tests/test_seed.py`.

## What you'll see in the UI

After the new seeder runs:

- The *Skills selected* table in the Teams tab no longer shows `—`
  in the `assigned_to` column for any skill that exists in the
  catalogue.
- The `assigned_to` value is the friendly agent label
  (e.g. `#017 — composites, layup`) produced by `_agent_label()` in
  `app.py`.

If you add new skills to `data/skills_seed.json`, just re-run
`seed_skills()` followed by `seed_agents(drop=True)` (or whatever
seeding helper you use). If the slot budget is too tight, the
sanity check raises a clear `RuntimeError` telling you to bump
`AGENT_SKILL_DISTRIBUTION`.

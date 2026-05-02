# skills.sh integration — research notes & pickup plan

> **Status:** investigation only, no code written. Captured 2026-05-02 during
> hackathon week so we can resume after the demo madness without losing
> context. The corresponding backlog item is the "Replace hand-authored
> `data/skills_seed.json` with 150 real skills.sh entries" line in
> [`docs/TODO.md`](TODO.md).

---

## 1. What skills.sh is

skills.sh is an **open agent-skills marketplace** operated by Vercel. It's a
public registry where developers publish reusable capabilities for AI agents
(Copilot, Claude Code, Cursor, etc.). At time of writing the homepage banner
reads **"All Time (90,990)"** — i.e. ~91 k skills, ranked by install count
via anonymous telemetry from the various agent runtimes that adopted the
format. (An earlier draft of this doc said ~8,420; that figure was wrong —
corrected 2026-05-02 against the live homepage.)

- Web UI:           https://skills.sh/
- Example skill:    https://skills.sh/vercel-labs/skills/find-skills
- CLI:              `npx skills` (skill discovery / install from the terminal)
- API (public):     `https://skills.sh/api/v1/skills`
- Each skill's source of truth is a **GitHub repo** containing a `SKILL.md`
  file with YAML frontmatter + markdown body.

The `find-skills` skill itself is a **human-facing search assistant**, not a
data-export endpoint. We initially thought it might serve as a connector;
it does not — see §6.

---

## 2. What a skills.sh "skill" looks like

### 2a. API representation (one document)

```json
{
  "id":          "vercel-labs/agent-skills/next-js-development",
  "name":        "Next.js Development",
  "description": "React and Next.js performance optimization guidelines...",
  "source":      "vercel-labs/agent-skills",
  "installs":    24531,
  "sourceType":  "github",
  "installUrl":  "https://github.com/vercel-labs/agent-skills",
  "url":         "https://skills.sh/vercel-labs/agent-skills/next-js-development"
}
```

### 2b. Source-repo representation (`SKILL.md`)

Each skill lives at the root of a GitHub repo (or in a subfolder of a
multi-skill repo such as `vercel-labs/agent-skills/<skill-name>/SKILL.md`)
and looks like:

```markdown
---
name: Next.js Development
description: React and Next.js performance optimization guidelines
author: vercel-labs
version: 1.2.0
---

# Long-form markdown body...
## Inputs / outputs / examples
```

So **two parsing paths exist**: API JSON (lightweight, no markdown body) and
the `SKILL.md` files themselves (full content, requires GitHub access).

---

## 3. Access mechanisms — ranked

| # | Mechanism            | Endpoint / Source                                   | Auth     | Rate limit                  | Verdict           |
|---|----------------------|-----------------------------------------------------|----------|-----------------------------|-------------------|
| 1 | **Public JSON API**  | `https://skills.sh/api/v1/skills` (paginated)       | ⚠ **unclear** | unverified                  | ⚠ verify auth first |
| 2 | GitHub repo clone    | `git clone https://github.com/<source>` then parse `SKILL.md` | none | GitHub API (60/hr unauth, 5k/hr keyed) | secondary, for full body |
| 3 | HTML scraping        | https://skills.sh/leaderboard et al.                | none     | de-facto via robots.txt     | viable fallback   |
| 4 | `find-skills` skill  | invoke as an agent skill                            | n/a      | n/a                          | ❌ not suitable (§6) |

> **Spot check 2026-05-02:** `curl https://skills.sh/api/v1/skills?per_page=1`
> returned **HTTP 401**. The subagent's earlier claim of "60 req/min unauth,
> 600 req/min keyed" is therefore **unverified**. Before committing to the
> JSON-API path, test with `npx skills` (which does work) and inspect the
> headers it sends; the API may require a Vercel session cookie or a key
> obtained via the CLI's first-run flow. If the API really is keyed-only,
> route #2 (clone the source GitHub orgs and parse `SKILL.md` files
> directly) becomes the recommended primary path — it's anonymous, stable,
> and gives us the full body for free.

> **Recommendation:** **JSON API for Phase 1**, optional `SKILL.md` parsing
> for Phase 2 to recover tags/category, optional GitHub `/repos/...` call for
> Phase 3 to fetch `github_stars`.

---

## 4. Suggested API calls (commands to run when we resume)

### 4a. List the top 150 skills (Phase 1 entrypoint)

```bash
# All-time leaderboard, 150 entries
curl -s 'https://skills.sh/api/v1/skills?view=all-time&per_page=150' | jq .

# Search filter (e.g. only data/ML skills)
curl -s 'https://skills.sh/api/v1/skills?q=embeddings&per_page=20' | jq .

# Pagination
curl -s 'https://skills.sh/api/v1/skills?per_page=50&page=2' | jq .
```

> ⚠ The exact pagination param names (`view`, `per_page`, `page`, `q`) were
> inferred by the research subagent from the public site behaviour. Confirm
> against the live API on first contact — there's no formal OpenAPI spec
> documented at the time of writing.

### 4b. Single-skill detail (full SKILL.md content if exposed)

```bash
curl -s 'https://skills.sh/api/v1/skills/vercel-labs/agent-skills/next-js-development' | jq .
```

### 4c. CLI alternative (no install, runs once)

```bash
npx skills list --limit 150 --json > skills_sh_dump.json
```

### 4d. GitHub stars (Phase 3, optional)

```bash
# Use a token: export GITHUB_TOKEN=...
gh api repos/vercel-labs/agent-skills --jq '.stargazers_count'
# or
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/repos/vercel-labs/agent-skills | jq .stargazers_count
```

### 4e. Quick scrape sanity check (only if API is unreachable)

```bash
curl -s 'https://skills.sh/' | grep -oE 'href="/[^"]+/skills/[^"]+"' | sort -u
```

---

## 5. Field-mapping — skills.sh → our `data/skills_seed.json`

| skills.sh field   | Our `skills_seed.json` field   | Mapping        | Notes                                                                  |
|-------------------|--------------------------------|----------------|------------------------------------------------------------------------|
| `name`            | `name`                         | direct ✅       | trivial                                                                |
| `description`     | `description`                  | direct ✅       | API gives the short summary; `SKILL.md` body has the full text         |
| `source`          | `repo_url`                     | derive ✅       | prefix with `https://github.com/`                                      |
| `id`              | `skill_id`                     | normalise ✅    | slug it: `vercel-labs/agent-skills/next-js-development` → `next-js-dev` |
| `installs`        | `installs`                     | ⚠ **divergent** | skills.sh = **cumulative**, our schema treats it as a usage signal. Either rename our field to `cumulative_installs` or convert via API delta sampling. **Affects Shapley `aᵢ` weighting** (`0.1·log(1+installs)/max`). |
| —                 | `tags[]`                       | ❌ missing      | Not in API. Recover from `SKILL.md` frontmatter (Phase 2) or infer via cosine over existing tag embeddings. |
| —                 | `category`                     | ❌ missing      | Same — derive in Phase 2.                                              |
| —                 | `github_stars`                 | ⚠ secondary     | Not on skills.sh; needs a GitHub API call per repo (Phase 3).          |
| —                 | `embedding` (1536-d)           | re-compute     | Re-embed `name + description` with `text-embedding-3-small` at ingest. |
| —                 | `prior_reputation`             | ❌ missing      | Has no source on skills.sh. Initialise to 0.5 or a normalised function of `log(installs)`. |

---

## 6. Why the `find-skills` skill is NOT the connector

The `find-skills` skill (https://skills.sh/vercel-labs/skills/find-skills) is
designed as a **discovery assistant for humans / agents inside an IDE**:

- Input: a free-text query like *"I need to build a Next.js dashboard"*.
- Output: a ranked, human-readable recommendation list authored by the
  surrounding LLM, citing skills from the registry.
- It returns **LLM prose**, not a structured payload.

Using it programmatically would mean:

1. instantiating an agent runtime that supports skills,
2. invoking `find-skills` with our subtask capability strings,
3. parsing the LLM's natural-language response back into structured records.

That's fragile (depends on LLM phrasing), expensive (per-skill LLM call), and
duplicates work the public API already does correctly for free. **Skip it.**

---

## 7. Recommended phased plan

### Phase 1 — Direct API import (effort: S, ~half a day)

1. New module `src/data/skills_sh_loader.py` with:
   - `fetch_top_skills(limit: int = 150) -> list[dict]` — paginated GET against
     `/api/v1/skills`.
   - `to_seed_record(api_doc: dict) -> dict` — field-map per §5, drop
     `tags`/`category`/`github_stars`/`prior_reputation` (or default them).
2. CLI: `python -m src.data.skills_sh_loader --limit 150 --out data/skills_seed.json`.
3. Re-run the existing seeding script (`scripts/seed_skills.py` or whatever
   the entrypoint is) so each new record gets re-embedded with
   `text-embedding-3-small` and indexed into Atlas.
4. Update `prior_reputation` initialisation: temporary heuristic
   `0.5 + 0.1·log10(1+installs) / log10(1+max_installs)` (clamped to [0, 1]).
5. Test: `pytest tests/ -q` — expect the matching tests to need new fixtures
   because skill IDs change. Update `tests/fixtures/skills_seed_subset.json`
   accordingly.

### Phase 2 — Recover `tags` / `category` from `SKILL.md` (effort: M)

1. For each skill, GET the raw `SKILL.md` from GitHub:
   `https://raw.githubusercontent.com/<source>/main/<path>/SKILL.md`.
2. Parse YAML frontmatter (`pyyaml`) — pull explicit `tags:`, `categories:`
   if present.
3. Where missing, infer tags by cosine-matching the embedding of the skill
   description against the embeddings of the *existing* hand-curated tags in
   `data/skills_seed.json`, taking the top-K above a threshold.

### Phase 3 — `github_stars` enrichment (effort: M)

1. For each unique `<owner>/<repo>` in the imported set, call
   `GET https://api.github.com/repos/<owner>/<repo>` and store
   `stargazers_count` in a new `github_stars` column.
2. Authenticate with a `GITHUB_TOKEN` env var (5 000 req/hr vs. 60/hr).
3. Cache results in MongoDB `skills_sh_cache` collection with TTL ≥ 24 h to
   avoid re-querying every seed.

---

## 8. Risks, unknowns, watch-outs

- **Schema stability** — skills.sh's API is young; no published SLA. Pin the
  fetched JSON snapshots into the repo (under `data/skills_sh_snapshots/`)
  for replay determinism.
- **Cumulative vs. weekly installs** — biggest semantic mismatch. Our
  Shapley `aᵢ` formula uses `0.1·log(1+installs)/max`. If we plug a
  cumulative number into a metric that should reflect *recent* signal, agents
  with old, popular skills will dominate. **Either**: (a) rename our field
  and accept the change, (b) compute weekly-delta by sampling the API on a
  cron, (c) replace the term in the formula with `log(stars)` once Phase 3
  lands.
- **Licensing & attribution** — every skill has its own GitHub licence.
  Surface the licence + source link in the UI alongside the skill card. Don't
  silently re-publish.
- **Embedding cost** — 150 skills × ~80 tokens ≈ 12 k tokens. At the
  `text-embedding-3-small` price (~$0.02 / 1 M tokens) this is well below
  $0.01. Negligible.
- **Rate-limit hygiene** — keep all skills.sh calls behind a small async
  client with `httpx.AsyncClient`, 5 concurrent reqs, exponential back-off
  on 429. No need for a dedicated key for Phase 1 (60/min covers the whole
  150-skill import in 3 minutes).
- **MongoDB index rebuild** — re-seeding the catalogue with 150 vs. the
  current ~36 skills will trigger an HNSW rebuild for
  `skills_embedding_vector`. Plan for ~1-2 min downtime on Atlas; do this on
  a feature branch + a scratch DB first.

---

## 9. Pickup checklist (resume after the hackathon)

When future-you sits down to resume this, in order:

1. [ ] Confirm the API still answers: `curl -s https://skills.sh/api/v1/skills?per_page=1 | jq .` returns a sane document.
2. [ ] Confirm the CLI still works: `npx skills --help` (sanity).
3. [ ] Pick the auth posture: anon for Phase 1, GITHUB_TOKEN for Phase 3.
4. [ ] Decide the `installs` semantics fix (rename / weekly-delta / drop). **Block on this — it changes the Shapley formula.**
5. [ ] Implement `src/data/skills_sh_loader.py` per §7 Phase 1.
6. [ ] Re-seed Atlas on a scratch DB; verify vector-search still ranks sanely against the canonical bridge prompt: *"design a 2 km bridge for 50 cars/h, modern aesthetic"*.
7. [ ] Update tests + fixtures.
8. [ ] If Phase 1 passes, ticket Phase 2 (`SKILL.md` parsing) and Phase 3 (GitHub stars) separately.

---

*Authored 2026-05-02 from a research-only investigation by a background
subagent. No production code was written; this document is the entire
deliverable from that pass.*

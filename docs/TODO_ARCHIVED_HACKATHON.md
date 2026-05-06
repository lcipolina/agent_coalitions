# TODO — *(archived 2026-05-06; hackathon-era)*

> **Frozen snapshot.** The hackathon is over. Active work is now tracked
> in [RESEARCH_PLAN.md](RESEARCH_PLAN.md), aimed at a paper submission
> using [WildClawBench](https://internlm.github.io/WildClawBench/) as
> the target benchmark. This file is preserved only to record what was
> planned and resolved during the 1-day MVP.

Tracked items deliberately deferred from the 1-day MVP. See `MVP_DESIGN.md` Amendments 2026-05-01 for the resolutions that produced these.

## Gate status (live)

- [x] G1 conda env
- [x] G2 config + secrets
- [x] G3 Mongo connectivity (13 collections + vector index)
- [x] G4 skills ingested (36 skills, 21 agents)
- [x] G5 Atlas Vector Search live
- [x] G6 mock pipeline end-to-end (12/12 tests green)
- [ ] G7 real-LLM pipeline (used for the demo video, not the live demo)
- [x] G8 Streamlit UI — live progress + 8 tabs + bridge elevation viz
- [x] G9 replay (zero LLM calls asserted by orchestrator)
- [x] G10 reputation persists across runs (`agents.reputation` accumulates)
- [ ] G11 demo script (≤90 s)

## Backlog

- [ ] Replace hand-authored `data/skills_seed.json` (~30–50 entries) with **150 real skills.sh entries**. (Q2)
    - **Investigation outcome (2026-05-02):** Feasible. skills.sh exposes a public JSON API at `https://skills.sh/api/v1/skills` (paginated, ~60 req/min unauth, 600/min with key) returning `{id, name, description, source, installs, sourceType, installUrl, url}` per skill. Each skill's source-of-truth is a GitHub repo with a `SKILL.md` (YAML frontmatter + markdown body).
    - **Recommended path:** Phase 1 (effort **S**) — `GET /api/v1/skills?view=all-time&per_page=150`, map `name → name`, `description → description`, `source → repo_url`, `installs → installs`; re-embed with `text-embedding-3-small`; upsert into the `skills` collection. Drop `tags[]`, `category`, `github_stars` for Phase 1 (no API source).
    - **Phase 2 (effort M):** parse each skill's `SKILL.md` to recover tags / category; infer missing tags via semantic similarity to existing catalogue tags.
    - **Phase 3 (effort M):** secondary GitHub `/repos/{owner}/{repo}` calls for `github_stars` (watch the 60/hr unauth limit; needs a token).
    - **Watch-outs:** skills.sh `installs` is *cumulative*, not weekly — adjust the Shapley `aᵢ` formula or rename the field to avoid the semantic mismatch. No SLA on schema stability. Respect per-skill licences when displaying attribution.
    - **Do NOT use:** the `find-skills` skill itself as a connector — it's a human-facing search UI that returns LLM prose, not parseable structured data.
- [ ] Replace mock LLM judge with the real LLM judge in mock-mode parity tests. The mock currently returns templated mid scores so the radar chart populates. (Q16)
- [ ] Run §11.2 strategy comparison (A: random, B: top-by-reputation, C: our mechanism) — implement gate **G12**.
- [x] AI hero render via OpenAI image API + "Concept render" tab — gate **G13**. *(Done 2026-05-06 — `src/pipeline/concept_render.py`, on-demand UI tab, mock-mode SVG placeholder so the demo never blanks out. Cherry-picked into `master` as `fecfc95`.)*
- [ ] Tighten validator: dynamic-load factor, fatigue check stub, deflection limit.
- [x] Cache LLM responses in Mongo `llm_cache` collection (Q12). *(On `master` — opt-in via `USE_LLM_CACHE`, default on; cache hits do not bump the LLM call counter, preserving G9 replay semantics.)*
- [ ] Verify "mock mode" is a single global flag inherited by every LLM call site (currently planned via `src.config.settings.use_mock_llm`); add a runtime assertion that no chat call goes out when the flag is true.

- [x] **Rename "blackboard" out of the codebase.** *(Done 2026-05-06.)* Module renamed to `src/agents/agent_comms.py`; canonical term is **agent comms** (UI tab) / **team message bus** (prose). Imports in `src/agents/marshal.py` and `src/pipeline/execution.py` updated; docstrings + comments scrubbed in `src/agents/agent_comms.py`, `src/agents/marshal.py`, `src/pipeline/execution.py`, `src/llm/mock.py`. Doc sweep applied to `MVP_DESIGN.md`, `LANGGRAPH.md`, `ARCHITECTURE.md`. MongoDB collection `coalition_messages` deliberately left unchanged.


## Out of scope (won't do)

These are deliberate non-goals — listed so the next person doesn't reopen the discussion.

- Distributed agent runtimes / MCP / A2A protocols — single Python process is the point.
- FEA, CAD, real engineering certification, AR/VR — the disclaimer covers it ("conceptual design … not certified engineering").
- Exact Shapley computation — the closed-form rank-1 / induced-subgraph value is the right tool here (see `docs/GAME_THEORY_PRIMER.md`).
- Authentication, rate limiting, deployment scripts, multi-tenancy.
- Tests beyond the four files in `MVP_DESIGN.md §8`.
- Bidding LLM calls or strategic agent behaviour — `MVP_DESIGN.md` Appendix A explains why this is *not* a market.

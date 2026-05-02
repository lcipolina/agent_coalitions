# TODO — post-hackathon backlog

Tracked items deliberately deferred from the 1-day MVP. See `MVP_DESIGN.md` Amendments 2026-05-01 for the resolutions that produced these.

## Hackathon gate status (live)

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

## Backlog (post-hackathon)

- [ ] Replace hand-authored `data/skills_seed.json` (~30–50 entries) with **150 real skills.sh entries**. (Q2)
- [ ] Replace mock LLM judge with the real LLM judge in mock-mode parity tests. The mock currently returns templated mid scores so the radar chart populates. (Q16)
- [ ] Run §11.2 strategy comparison (A: random, B: top-by-reputation, C: our mechanism) — implement gate **G12**.
- [x] AI hero render via OpenAI image API + "Concept render" tab — gate **G13**. *(Done on `feat/concept-render-and-cache` branch — `src/pipeline/concept_render.py`, on-demand UI tab, mock-mode SVG placeholder so the demo never blanks out. Not yet merged into `master`.)*
- [ ] Tighten validator: dynamic-load factor, fatigue check stub, deflection limit.
- [x] Cache LLM responses in Mongo `llm_cache` collection (Q12). *(Done on `feat/concept-render-and-cache` branch — opt-in via `USE_LLM_CACHE`, default on; cache hits do not bump the LLM call counter, preserving G9 replay semantics. Not yet merged into `master`.)*
- [ ] Verify "mock mode" is a single global flag inherited by every LLM call site (currently planned via `src.config.settings.use_mock_llm`); add a runtime assertion that no chat call goes out when the flag is true.

- [ ] **Rename "blackboard" out of the codebase.** The term confused hackathon judges and is jargon we'd rather drop. Replace with `agent_comms` / `team message bus` / `message log` (pick one and use it consistently). Concretely:
    - Rename module `src/agents/blackboard.py` → `src/agents/agent_comms.py` (or `team_messages.py`); update all imports (`src/agents/marshal.py`, `src/pipeline/execution.py`, tests).
    - Rewrite docstring on line 1 of the renamed module ("Blackboard helpers — post / read / render…").
    - Strip the word from comments in `src/llm/mock.py:89`, `src/agents/marshal.py:15`, `src/pipeline/execution.py:1` and `:241`.
    - Sweep `docs/` for any remaining occurrences (`MVP_DESIGN.md`, `GAME_THEORY_PRIMER.md`, `MATCHING_PIPELINE.md`, `LANGGRAPH.md`, …) and replace with the chosen canonical term.
    - Keep the MongoDB collection name `coalition_messages` as-is (renaming a live collection is a migration, not a rename).
    - Verify with `grep -ri "blackboard" .` returning zero matches outside historical changelog/commit-message references.

- [x] Implement LangGraph behind a `USE_LANGGRAPH` flag, with sidebar toggle, status badge, Workflow tab and `docs/LANGGRAPH.md`. *(Done — merged into `master` on demo day; the package is now an optional dependency, the toggle disables itself if the package is missing.)*

## Out of scope (won't do)

These are deliberate non-goals — listed so the next person doesn't reopen the discussion.

- Distributed agent runtimes / MCP / A2A protocols — single Python process is the point.
- FEA, CAD, real engineering certification, AR/VR — the disclaimer covers it ("conceptual design … not certified engineering").
- Exact Shapley computation — the closed-form rank-1 / induced-subgraph value is the right tool here (see `docs/GAME_THEORY_PRIMER.md`).
- Authentication, rate limiting, deployment scripts, multi-tenancy.
- Tests beyond the four files in `MVP_DESIGN.md §8`.
- Bidding LLM calls or strategic agent behaviour — `MVP_DESIGN.md` Appendix A explains why this is *not* a market.

# TODO — post-hackathon backlog

Tracked items deliberately deferred from the 1-day MVP. See `MVP_DESIGN.md` Amendments 2026-05-01 and `PLAN.md §3` for the resolutions that produced these.

- [ ] Replace hand-authored `data/skills_seed.json` (~30–50 entries) with **150 real skills.sh entries**. (Q2)
- [ ] Replace mock LLM judge with the real LLM judge in mock-mode parity tests. The mock currently returns templated mid scores so the radar chart populates. (Q16)
- [ ] Run §11.2 strategy comparison (A: random, B: top-by-reputation, C: our mechanism) — implement gate **G12**.
- [ ] AI hero render via OpenAI image API + "Concept render" tab — gate **G13**.
- [ ] Consider §A.4 truthful-reporting incentive mechanism (declared confidence + ex-post penalty) — only after that does the word *market* become defensible.
- [ ] Tighten validator: dynamic-load factor, fatigue check stub, deflection limit.
- [ ] Cache LLM responses in Mongo `llm_cache` collection (currently skipped per Q12).
- [ ] Verify "mock mode" is a single global flag inherited by every LLM call site (currently planned via `src.config.settings.use_mock_llm`); add a runtime assertion that no chat call goes out when the flag is true.

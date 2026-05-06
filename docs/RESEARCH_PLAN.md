# Research Plan — Beating WildClawBench with Coalition-Selected Skills

**Status:** active (post-hackathon, 2026-05-06).
**Replaces:** `TODO.md` (archived; the hackathon is over).

---

## 0. One-sentence thesis

Shapley-weighted skill coalitions, selected per-task from a catalog of
skills.sh skills, beat both *all-skills-installed* and
*top-K-by-individual-reputation* baselines on
[WildClawBench](https://internlm.github.io/WildClawBench/) when controlling
for the base LLM.

The mechanism we built for the MongoDB hackathon (matching pipeline +
closed-form Shapley over a skill graph) is the prototype. The paper turns
it into a quantified result on a public leaderboard.

---

## 1. Target benchmark — what it is and why it fits

**WildClawBench** (InternLM, 2026, MIT). 60 hand-built tasks in 6
categories, each running inside a Docker container with the
[OpenClaw](https://github.com/openclaw/openclaw) personal-assistant
environment (browser, bash, file system, email, calendar).

| Category             | N  | Example tasks                                                                    | Skill-axis hypothesis                                |
|----------------------|----|----------------------------------------------------------------------------------|------------------------------------------------------|
| Productivity Flow    | 10 | ArXiv digest, PDF batch classify, calendar scheduling, LaTeX table extraction    | PDF-parser, email, calendar, ArXiv search            |
| Code Intelligence    | 12 | SAM3 inference from source, visual puzzles, benchmark reproduction               | Code-reading, dependency-install, image processing   |
| Social Interaction   |  6 | Multi-round meeting negotiation, escalation routing                              | Email, calendar, conversation memory                 |
| Search & Retrieval   | 11 | Conflict resolution across sources, financial extraction, fuzzy repo search      | Brave search, web crawl, dedup                       |
| Creative Synthesis   | 11 | Football match report w/ video clips, paper-to-poster, outfit-to-model image    | Video editing, image gen, layout                     |
| Safety Alignment     | 10 | Prompt injection in files, leaked-API-key detection, malicious skill injection  | Static analysis, secret scanning, refusal heuristics |

**Why this benchmark:**

1. **Skill-decomposable.** Tasks naturally need different *bundles* of
   skills — exactly what coalition formation optimises.
2. **Headroom.** Top frontier model (Claude Opus 4.6) only reaches 51.6 %.
   There is real room above the SOTA single-model line.
3. **Public submission lane.** The "Personal OpenClaw Leaderboard"
   ("lobsters") accepts user-submitted configs of
   `SOUL.md / USER.md / MEMORY.md / skills/`. We submit a config built
   by our matching pipeline; result is independently verifiable.
4. **MIT-licensed, reproducible.** Same Docker image, same data, same
   grader for everyone.
5. **Skill format we already speak.** OpenClaw consumes skills.sh skills
   (SKILL.md + YAML frontmatter), which is the same catalog the deferred
   ingestion TODO already pointed at.

---

## 2. Phases

### Phase A — Skill catalog audit (effort: M, ~1 week)

**Goal:** know what's actually in skills.sh and how it maps to
WildClawBench task categories.

- [ ] **A1.** Pull the full skills.sh catalog via the documented JSON API
      (`GET https://skills.sh/api/v1/skills?view=all-time&per_page=500`).
      Persist raw responses to disk for reproducibility.
- [ ] **A2.** Build a category histogram. The skills.sh catalog tags
      skills with categories and source-types — count distribution,
      median description length, fraction with usable `installUrl`.
- [ ] **A3.** For each WildClawBench category (6 of them), hand-rate
      the top-50 candidate skills by relevance (3-point scale).
      Output: `data/skills_x_wildclaw.csv`. This is the *human prior*
      we will compare the embedding-based matcher against.
- [ ] **A4.** Re-embed the full catalog with `text-embedding-3-small`
      and load into our existing `skills` collection. Reuse the Atlas
      Vector Search index `skills_embedding_vector`.
- [ ] **A5.** For each WildClawBench category, run an exemplar task
      description through the existing `matcher.find_skills` and check
      top-K overlap with the human prior from A3.
      *Pass criterion:* recall@20 ≥ 0.6 against the human shortlist.

**Deliverable:** a short note `docs/SKILL_AUDIT.md` reporting catalog
size, category coverage, and matcher recall on the human prior.

### Phase B — Adapter to WildClawBench (effort: M, ~1 week)

**Goal:** drive the WildClawBench evaluator with our coalition mechanism
under the "Personal OpenClaw Evaluation" submission interface.

- [ ] **B1.** Clone `InternLM/WildClawBench`. Reproduce the baseline run
      end-to-end on one task (ideally one cheap Productivity Flow task)
      with the default skill bundle; record `score.json`, `usage.json`,
      and elapsed time.
- [ ] **B2.** Write a thin adapter (`src/wildclaw/lobster_builder.py`)
      that, given a task description, queries our matcher and produces
      a workspace tree (`SOUL.md`, `MEMORY.md`, `skills/<chosen…>/…`)
      formatted exactly as `--lobster-workspace` expects.
- [ ] **B3.** Smoke-test the adapter on the same single task from B1.
      Confirm the agent runs, the chosen skills get loaded, and the
      grader returns a score (any score — pass criterion is *no
      crash*, not improvement).
- [ ] **B4.** Wrap with a small CLI:
      `python -m src.wildclaw.run --strategy {all,topk,coalition}
       --model openrouter/<x> --category 01_Productivity_Flow`.

**Deliverable:** reproducible single-task run with our skill picker; one
new column in `output/summary_all_<…>.json` (`our_strategy`).

### Phase C — Strategy comparison study (effort: L, ~2–3 weeks)

**Goal:** the headline result for the paper.

For each of *N* base models (start with 3: a strong open one
like Qwen3.5-397B, a cheap one like Step 3.5 Flash, and one frontier
proprietary via OpenRouter):

| Strategy             | Description                                                                |
|----------------------|----------------------------------------------------------------------------|
| **vanilla**          | No extra skills installed (model only). Floor.                              |
| **all**              | All catalog skills installed in the lobster. Greedy upper baseline.         |
| **topK-popularity**  | Top-K skills by skills.sh `installs`. Crowd prior.                          |
| **topK-similarity**  | Top-K by cosine similarity of task description to skill description.        |
| **coalition (ours)** | Marshal + closed-form Shapley pick of K skills from the matched candidates. |

- [ ] **C1.** Settle K. Plot per-task accuracy vs. K on a held-out 10 %
      slice; pick the elbow.
- [ ] **C2.** Run all 60 tasks × 3 models × 5 strategies × 3 seeds = 2700
      task runs (budget-permitting). The replay cache `llm_cache`
      collection is your friend — most embedding calls deduplicate.
- [ ] **C3.** Primary statistic: *paired* score difference per task
      between **coalition** and each baseline. Report Wilcoxon
      signed-rank p-values per category.
- [ ] **C4.** Secondary statistic: cost in USD and wall-clock time
      (these are in `usage.json`). Coalition is allowed to win on
      "Pareto frontier of score vs. cost", not only raw score.
- [ ] **C5.** Submit the best coalition lobster to
      wildclawbench@proton.me for an independent verification on the
      Personal OpenClaw Leaderboard.

**Deliverable:** `docs/RESULTS.md` with score tables, Pareto plots,
and the leaderboard submission identifier.

### Phase D — Ablations (effort: M, ~1 week)

The reviewer questions we know are coming.

- [ ] **D1.** Replace closed-form Shapley with exact Shapley on a 6-agent
      subset; quantify the approximation gap on a held-out 5-task
      slice. Pass criterion: rank correlation ≥ 0.85.
- [ ] **D2.** Ablate the synergy term (`λ` weight on pairwise edges).
      Setting λ=0 should reduce the picker to plain similarity ranking.
- [ ] **D3.** Ablate the reputation update. Run the full 60-task suite
      twice — once where `agents.reputation` is frozen at 1.0, once
      where it accumulates across tasks. Quantify the *learning* effect.
- [ ] **D4.** Cross-model robustness. The strategy should not require
      hyperparameter retuning per base LLM. Show curves overlap.

### Phase E — Paper (effort: L, ~3–4 weeks)

Target venue (in priority order):

1. **NeurIPS Datasets & Benchmarks track** (Jul deadline, fits "method
   on a public benchmark" framing).
2. **ICLR** (Sep deadline; the agent-systems track is hot in 2026).
3. **AAMAS** if the multi-agent / coalition-game framing is leading.
4. arXiv first regardless.

Sections:

1. Intro — agents-as-skills view; problem of skill bloat.
2. Related work — single-agent benchmarks (HumanEval, SWE-bench),
   multi-agent (AutoGen, CAMEL), skill / tool selection, cooperative
   game theory in ML.
3. Method — the matching pipeline (already documented in
   `MATCHING_PIPELINE.md`); closed-form Shapley
   (`GAME_THEORY_PRIMER.md`); reputation update.
4. Experimental setup — WildClawBench, models, baselines, metrics.
5. Results — Phase C tables.
6. Ablations — Phase D.
7. Discussion — when does the mechanism fail (Safety Alignment
   tasks where skill choice is dominated by refusal-heuristic).
8. Conclusion + future work (online learning, cross-benchmark transfer).

---

## 3. Open methodological questions (need an answer before C runs)

1. **Reputation cold-start.** WildClawBench tasks are diverse; one task's
   "success" doesn't trivially predict another's. Do we initialise
   `reputation` per (skill, category) instead of per skill?
2. **Coalition size budget.** OpenClaw has token-budget pressure once
   `skills/` grows past ~10 entries (each skill loads its SKILL.md into
   the system prompt). What is the ceiling K and is it model-dependent?
3. **Task→prompt mapping.** WildClawBench gives a structured
   `task.md` per task. Do we feed the whole thing to our decomposer or
   just the goal section? Pre-test this on 5 tasks before scaling up.
4. **Stochasticity.** WildClawBench scores are averaged over multiple
   runs in the public leaderboard. We need ≥3 seeds per cell or any
   "improvement" we report is noise.
5. **Cost ceiling.** Phase C is expensive if any cell uses Claude Opus
   4.6. Plan to run *only the best two strategies* on the expensive
   model and the full grid on cheap models.

---

## 4. Operational notes

- `master` is at `fecfc95` (concept-render + llm_cache merged).
  17/17 tests green. Live Streamlit demo deployed.
- `data/llm_replay_cache.json` is the hackathon replay cache; do not
  rely on it for paper experiments — those need real-mode calls.
- Atlas free-tier cluster auto-pauses after 60 days. Run
  `scripts/check_mongo.py` weekly during the experiment phase.
- Rotate the MongoDB password and OpenAI API key before any external
  data sharing or paper submission (both were pasted in a chat
  transcript on 2026-05-06).

---

## 5. Out of scope (deliberate non-goals)

- Beating the *single-model* SOTA on WildClawBench by switching to a
  better base LLM. We're studying skill-selection mechanisms, not
  models.
- Real-time online skill discovery (scraping new skills mid-task).
  Catalog is fixed at experiment start.
- Multi-agent coordination *within* a WildClawBench task. OpenClaw
  is single-agent; our coalition is over *skills*, not over agents
  in the runtime sense. (This was a confusing point in the
  hackathon project; it's clearer in the paper framing.)
- Reproducing the full WildClawBench 60-task suite from scratch.
  We use the published Docker image and grader.

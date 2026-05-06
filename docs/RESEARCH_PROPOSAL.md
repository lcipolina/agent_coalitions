# Research Proposal — Coalition-Selected Skills for Agent Benchmarks

**Status:** living document, post-hackathon (2026-05-06).
**Target venues (priority order):** NeurIPS Datasets & Benchmarks 2026,
ICLR 2027, AAMAS 2027, arXiv preprint regardless.
**Operational plan:** [RESEARCH_PLAN.md](RESEARCH_PLAN.md) (this proposal
defines the *why* and *what*; the plan defines the *how* and *when*).

---

## 1. Executive summary (TL;DR)

We claim that **principled skill-bundle selection** — choosing which
skills (in the OpenClaw / `SKILL.md` sense) to install in an agent's
workspace before each task — is a more impactful intervention on agent
benchmark scores than the literature acknowledges. We formalise the
selection problem as a **cooperative-game-theoretic coalition
formation** over a retrieved candidate set, with a closed-form Shapley
solution and a reputation accumulator that learns from past task
outcomes.

We evaluate on two public agent benchmarks
([WildClawBench](https://internlm.github.io/WildClawBench/) primary,
[GAIA](https://huggingface.co/gaia-benchmark) secondary) and report
score lift across five strategies (vanilla, all-retrieved, top-K
similarity, top-K popularity, **coalition (ours)**) for three base
models spanning a 12× cost range. The headline claim is *not* a new
absolute SOTA — it is a **Pareto-frontier dominance result in the
mid-cost regime**, plus a per-category cost-equivalence claim ("our
$6 submission matches a $80 frontier-model score on Search & Retrieval
tasks").

---

## 2. Problem statement

### 2.1 The skill-selection problem

Modern agent runtimes (OpenClaw, Claude Code, Claude Desktop with
Skills, Anthropic's "Skills" launch, the broader skills.sh ecosystem)
load a bundle of skills — markdown files with YAML frontmatter
declaring `name`, `description`, `dependencies`, `triggers` — into the
agent's system prompt before each task. The bundle determines:

- Which tools the agent knows it can call.
- Which workflows the agent treats as canonical.
- Which constraints (refusals, citation requirements, formatting) it
  inherits.

Empirically, **skill bundle has first-order impact on benchmark scores
when the base model is fixed**. Yet the standard practice is one of
two extremes:

- **Install nothing** — the model relies on internal knowledge and
  generic tool use. Floor.
- **Install everything (or a hand-picked default set)** — the system
  prompt bloats; relevant signal is buried; performance plateaus or
  regresses.

There is no principled middle ground. Picking the right ~5–10 skills
*per task* from a catalog of thousands is currently a manual,
per-submission engineering exercise. **We want to automate it
in a way that is:**

1. **Adaptive** — the bundle depends on the task description.
2. **Synergy-aware** — `pdf` + `paper-context-resolver` together are
   more useful than either alone, and the picker should know this.
3. **Learning** — past task outcomes inform future bundles (a skill
   that helped on similar tasks gets boosted).
4. **Bounded** — total bundle size respects the prompt-budget ceiling.

### 2.2 Why this is a coalition-formation problem

The four desiderata above map directly onto the structure of
**cooperative game theory** with a value function $v: 2^S \to
\mathbb{R}_{\ge 0}$ over subsets of a skill set $S$:

- **Adaptive** ⇒ $v$ depends on the task instance (a non-trivial
  conditional value function).
- **Synergy-aware** ⇒ $v$ is super-additive on relevant pairs:
  $v(\{i, j\}) > v(\{i\}) + v(\{j\})$ for complementary skills.
- **Learning** ⇒ the per-skill marginal contribution must be
  estimable from data — the **Shapley value** is the canonical
  fair-division attribution.
- **Bounded** ⇒ the optimisation is over $S^* \subseteq S$ with
  $|S^*| \le K$.

Hence the natural mathematical object is the **constrained
Shapley-maximising coalition**:

$$
S^*(t) = \arg\max_{|S'| \le K} \sum_{i \in S'} \varphi_i(v_t)
$$

with a closed-form rank-1 approximation
$\varphi_i \approx a_i + \tfrac{1}{2} \sum_j w_{ij}$ that we already
implemented for the hackathon (full derivation in
[GAME_THEORY_PRIMER.md](GAME_THEORY_PRIMER.md)).

### 2.3 Why now

Three timing factors make this a 2026 publication:

1. **WildClawBench released two months ago** with no published
   skill-selection baselines. The Personal OpenClaw Leaderboard
   ("lobsters") explicitly invites custom skill submissions.
2. **Skills.sh and similar registries are scaling rapidly** — 90k+
   skills advertised, 189 visible on the homepage as of May 2026.
   Naive "install everything" is no longer tenable.
3. **No paper formalises the problem** as we just did. The closest
   prior work treats tool selection as a retrieval / RAG problem
   (top-K cosine), missing the synergy and reputation axes.

---

## 3. Contributions

We claim four:

| # | Contribution | Evidence |
|---|---|---|
| **C1** | **Formalisation.** Skill-bundle selection cast as a constrained Shapley-maximising coalition with closed-form approximation. | §2.2; full math in `GAME_THEORY_PRIMER.md`. |
| **C2** | **Mechanism.** A retrieve→Shapley→reputation pipeline implemented end-to-end (~2k LOC, MongoDB-backed, mock-replayable). | Existing hackathon codebase; see `MATCHING_PIPELINE.md`. |
| **C3** | **Empirical result.** On WildClawBench, our mechanism delivers +X to +Y points over four naive baselines on three base models, dominating the cost-vs-score Pareto frontier in the $5–$15/run regime. | Phase C of `RESEARCH_PLAN.md`. |
| **C4** | **Cross-benchmark generalisation.** The same mechanism, with no hyperparameter retuning, achieves comparable lift on GAIA (Level 1–2). | Phase C-secondary. |

(C1 alone is a workshop paper; C1+C2+C3 is a main-conference paper;
adding C4 makes it a strong Datasets & Benchmarks track submission.)

---

## 4. Method overview

The pipeline that produces a skill bundle for one task:

```
task description
     │
     ▼
┌────────────────────────────────────────────┐
│ 1. RETRIEVE                                │
│    Atlas Vector Search over C_full         │
│    (~5–10k embedded SKILL.md descriptions).│
│    Returns C_taskpool: top-20 candidates.  │
└────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│ 2. ESTIMATE pairwise synergy w_ij          │
│    via either (a) co-occurrence in past    │
│    successful runs, or (b) cosine similarity│
│    of skill descriptions, or (c) explicit   │
│    `dependencies` field in SKILL.md YAML.   │
└────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│ 3. RANK by closed-form Shapley             │
│    φ_i ≈ a_i + (1/2) Σ_j w_ij              │
│    with a_i = (αs_i + βr_i + γc_i)         │
│    s_i: similarity, r_i: reputation,       │
│    c_i: install-count prior.               │
└────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│ 4. SELECT K via greedy under coverage and  │
│    diversity constraints (MAX_K=10 for     │
│    OpenClaw token budget).                 │
└────────────────────────────────────────────┘
     │
     ▼
   S*(task) — write SKILL.md files into
   --lobster-workspace/skills/
```

The mechanism is implemented and tested
(17/17 tests green; live demo at
[lcipolina/agent_coalitions](https://github.com/lcipolina/agent_coalitions)).
What changes for the paper is the *catalog* (now ~5k skills, not the
hackathon's 70) and the *target benchmarks* (WildClawBench + GAIA, not
synthetic bridge prompts).

---

## 5. Experimental design

### 5.1 Catalogs

Three nested catalogs, used at different stages:

| Catalog | Size | Built how | Used for |
|---|---|---|---|
| **C_full** | ~5–10k | skills.sh API (auth) + GitHub `path:SKILL.md` search + `awesome-claude-skills` lists | Atlas Vector Search index (the retrieval haystack). |
| **C_curated_50** | ~50 | The R≥1 entries from `data/audit/skills_x_wildclaw.csv` (human prior) | **Ablation only** — sanity-check baseline that lets us isolate retrieval's contribution. |
| **C_taskpool** | 20 per task | `matcher.find_skills(task, k=20)` against C_full | Input to the coalition picker for that task. |

**Critical insight (per recent feedback):** scaling C_full is part of
the method, not a nuisance variable. Naive top-K cosine baselines are
*hurt* by larger catalogs (more confidently irrelevant neighbours);
our mechanism should be *helped* by them (more candidates for synergy
computation). Phase D5 catalog-size ablation tests this directly.

### 5.2 Strategies (the 5 cells per (model, benchmark, task) tuple)

All strategies receive the same `C_taskpool` (top-20 retrieved). They
differ only in how they pick the final $K$:

| Strategy | Rule | Role |
|---|---|---|
| `vanilla` | Install nothing. | Floor. |
| `all-retrieved` | Install all 20. | Greedy upper / token-bloat baseline. |
| `topK-similarity` | Top-K by cosine. | Standard RAG baseline. |
| `topK-popularity` | Re-rank by `installs` count, top-K. | Crowd prior baseline. |
| **`coalition (ours)`** | Constrained Shapley. | Our method. |

### 5.3 Models

Three base models spanning the cost spectrum (prices from the
WildClawBench leaderboard, May 2026):

| Model | Cost / WCB run | WCB stock score | Why include |
|---|---|---|---|
| Step 3.5 Flash (StepFun) | $6.63 | 26.7 % | Cheapest. Skill curation should help most here (the H4 hypothesis). |
| Kimi K2.5 (Moonshot) | $6.73 | 30.8 % | Strong open-source model. The "credible budget option." |
| Qwen 3.5 397B (Alibaba) | $22.33 | 34.5 % | Mid-tier. Tests whether lift persists into stronger models. |

(We deliberately exclude Claude Opus 4.6 / GPT-5.4 / Gemini 3.1 from
the main grid for cost reasons. Phase D6 includes a single "frontier
sanity" run on the best two strategies with a frontier model to
confirm the lift survives — but the main result is the cheap-model
Pareto.)

### 5.4 Primary benchmark — WildClawBench

- 60 tasks, 6 categories: Productivity Flow (10), Code Intelligence
  (12), Social Interaction (6), Search & Retrieval (11), Creative
  Synthesis (11), Safety Alignment (10).
- Public Personal OpenClaw Leaderboard accepts custom-workspace
  submissions.
- Grader runs after the agent finishes; ground truth is hidden during
  execution. Reproducible.

### 5.5 Secondary benchmark — GAIA

[GAIA](https://huggingface.co/spaces/gaia-benchmark/leaderboard)
(Mialon et al., 2023, Meta AI) — *General AI Assistants* — 466 real
questions, 3 difficulty levels.

**Why GAIA as the secondary:**

- Established benchmark with active leaderboard and many published
  baselines (FAIR's original AutoGPT scores, HuggingFace's
  `smolagents`, Trase Agent, Sibyl, etc.).
- Tasks span web search, file analysis, spreadsheets, audio, image
  reasoning — overlapping but not identical to WCB's category split.
- Skills.sh entries we already identified for WCB (firecrawl-*, pdf,
  xlsx, browser-use) are also relevant for GAIA. **Same catalog,
  different benchmark** — that's the cleanest possible
  generalisation claim.
- Published Level-1 SOTA (~75 %), Level-2 ~50 %, Level-3 ~30 % give us
  clear targets.

**Alternative secondary benchmarks considered, rejected:**

- *τ-bench* (Sierra): too narrow (airline + retail customer-service
  only); overfits the "tool selection" framing.
- *AgentBench*: 2023, increasingly stale; skill-bundle framing isn't
  natural fit.
- *TheAgentCompany*: long-horizon, expensive runs, hard to replicate
  in a paper budget.
- *OSWorld* / *WebArena*: GUI-heavy; OpenClaw-style skill bundles
  don't directly apply.

### 5.6 Metrics

Per `(strategy, model, benchmark, task, seed)` cell we record:

- **Score** (0–1, per benchmark's own grader).
- **Cost** (USD; from `usage.json` for WCB, OpenAI billing API for
  GAIA).
- **Wall-clock time** (seconds).
- **Bundle size** $|S^*|$ and bundle composition (logged for
  qualitative analysis).
- **Replay-cache hit rate** (for cost amortisation reporting).

Aggregations:

- **Per-category mean score** (primary table).
- **Pareto plot** score vs cost across all `(strategy, model)` points.
- **Paired Wilcoxon signed-rank** between coalition and each baseline
  on per-task scores.
- **Spearman rank correlation** of bundle ranking between
  closed-form Shapley and exact Shapley (D1 ablation, on a small
  subset).

Three seeds per cell. Total runs = 5 strategies × 3 models × (60 +
466) tasks × 3 seeds ≈ **23,670 task runs**. With caching, real LLM
calls are ~1/3 of that. Budget estimate §11.

---

## 6. Ablations (Phase D)

| ID | Ablation | Tests | Pass criterion |
|----|----------|-------|----------------|
| D1 | Closed-form Shapley vs exact Shapley | Approximation gap | Spearman ≥ 0.85 on 6-skill subset |
| D2 | Synergy weight λ ∈ {0, 0.2, 0.4, 0.6, 0.8} | Importance of pairwise terms | λ=0 reduces to top-K-similarity (sanity) |
| D3 | Reputation freeze vs accumulate | Importance of learning | Accumulate beats freeze by ≥2 pts on a hold-out task slice |
| D4 | Cross-model robustness | No retuning needed across models | Same hyperparameters work for all 3 |
| **D5** | **Catalog size: $|C_{full}| \in \{50, 500, 5000\}$** | **The reviewer-killer ablation** | **Coalition advantage *grows* with catalog size; baselines plateau or regress** |
| D6 | Frontier-model sanity | Does lift survive on Claude Opus / GPT-5.4? | Coalition still beats `topK-similarity` by ≥1 pt on best 2 strategies |
| D7 | $K$ sensitivity | Optimal bundle size | Concave curve with elbow at K∈[5, 10] |
| D8 | Per-category reputation | $(skill, category)$ vs $skill$ alone | Per-category beats global by ≥1 pt on cross-category tasks |

D5 is the **load-bearing ablation**. If it succeeds, the paper writes
itself — large catalog + naive retrieval breaks; large catalog + our
mechanism doesn't.

---

## 7. Hypotheses with magnitudes

(Pre-registered before running Phase C; see `RESEARCH_PLAN.md` §3.)

| ID | Hypothesis | Expected magnitude |
|----|------------|--------------------|
| H1 | Coalition > `topK-similarity` on Search & Retrieval | +5 to +8 points |
| H2 | Coalition > `all-retrieved` on Productivity Flow | +3 to +6 points (token-budget effect) |
| H3 | No mechanism ≫ `vanilla` on Safety Alignment | All within ±1 point (a *negative* result we'll report honestly) |
| H4 | Lift larger on cheap models than mid-tier | +8 (Step 3.5 Flash) vs +3 (Qwen 3.5) |
| H5 | Lift transfers to GAIA Level 1–2 | +4 to +7 points |
| H6 | Catalog size × strategy interaction | At $|C_{full}| = 5000$, naive top-K ≤ vanilla (it picks noise); coalition > top-K by ≥6 points |

---

## 8. The "wow" angle (without absolute leaderboard #1)

The user's instinct that absolute-#1-on-the-main-leaderboard is the
flashiest result is correct. We won't get there (Claude Opus 4.6 is
out of budget). But there are three replacement "wow" hooks, all
defensible:

### 8.1 Cost-equivalent frontier match

The headline plot:

> *Score vs cost (USD/run, log scale). Our submissions occupy the
> Pareto frontier in the [$5, $15] regime, and **on Search &
> Retrieval specifically, our $6 Step-3.5-Flash + coalition submission
> matches the $80 Claude Opus 4.6 stock score**.*

That sentence + that plot is a tweet, a blog post, and a NeurIPS
poster all at once.

### 8.2 #1 on Personal OpenClaw Leaderboard for cheap models

Among `Step 3.5 Flash` and `Kimi K2.5` lobster submissions, take
**top spot**. Smaller pond, but a real public leaderboard #1.

### 8.3 First paper to formalise the problem

WildClawBench released two months ago. There is *no* prior published
work on principled skill selection over its skills format. **First-mover
formalisation is itself a wow.** "First to characterise X as a
coalition game" tends to age well.

The combination of 8.1 + 8.2 + 8.3 is a stronger pitch than "absolute
top of leaderboard": defensible, reproducible, *and* eye-catching.

---

## 9. Target venues

In priority order:

| Venue | Track | Deadline | Fit |
|-------|-------|----------|-----|
| **NeurIPS 2026** | Datasets & Benchmarks | June 2026 | Excellent — paper introduces no new dataset but a new evaluation methodology on two existing benchmarks; track explicitly accepts "method on benchmark" submissions. |
| **ICLR 2027** | Main | September 2026 | Strong — agent-systems and tool-use are hot 2026 topics. |
| **AAMAS 2027** | Main | November 2026 | Niche but apt — coalition-formation framing is exactly AAMAS audience. |
| **ICML 2027** | Main | February 2027 | Backup — more ML-theory-leaning; Shapley story plays here. |
| **arXiv** | Preprint | Immediately on Phase C completion | Always do this regardless. |

---

## 10. Risks and open questions

### 10.1 Methodological risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Coalition lift falls inside noise (<2 pts) | Medium | Pre-register hypotheses; 3 seeds; paired Wilcoxon |
| Closed-form Shapley diverges too far from exact | Low | D1 ablation; if fail, fall back to permutation Shapley with k=200 samples |
| OpenClaw token budget caps lift | Medium | D7 K-sensitivity; pre-test K in {3,5,8,10,15} |
| GAIA generalisation fails | Medium | If H5 fails, paper still stands as a WCB-only result; reframe contribution as "WCB-specific" |
| Reviewer demands *online* skill authoring | Low (but vocal) | Section 7 "future work" pre-empts; cite as scope choice |

### 10.2 Operational risks

| Risk | Mitigation |
|------|-----------|
| Mongo Atlas free-tier auto-pauses | `scripts/check_mongo.py` weekly; free-tier eventually upgrade to M10 ($60/mo) for experiment phase |
| skills.sh API key not granted | Crawl GitHub directly via `path:SKILL.md` code search; slower but works |
| OpenAI rate limits on embeddings | Batch + cache; `text-embedding-3-small` is cheap and parallelisable |
| Budget overrun | Hard cap per-cell; switch to `gpt-4o-mini` if run cost trends above forecast |

### 10.3 Open methodological questions (must answer before Phase C)

1. **Per-category reputation cold-start.** Initialise per-(skill,
   category) with a Bayesian prior or with cross-category transfer?
2. **Synergy weight estimation.** Three options in §4 step 2 — pick
   one for the main result, ablate the others.
3. **Task→prompt mapping.** Decompose WCB `task.md` files or pass
   wholesale? Pre-test on 5 tasks per category.
4. **GAIA file inputs.** GAIA tasks ship with attached files; need a
   skill or a hook that mounts these into the OpenClaw container.

---

## 11. Resource estimate

### 11.1 API budget

| Item | Calls | Unit cost | Subtotal |
|------|-------|-----------|----------|
| Embedding C_full once (~10k × ~500 tokens) | 5M tokens | $0.02/1M | $0.10 |
| Re-embedding on catalog updates × 3 | 15M | $0.02/1M | $0.30 |
| Phase C — WCB (3 models × 5 strategies × 60 tasks × 3 seeds) | 2700 runs | weighted avg ~$5 | ~$13,500 |
| Phase C — GAIA (3 models × 5 strategies × 466 × 3 seeds) | 21,000 runs | ~$2 | ~$42,000 |
| Cache amortisation | — | 30–50 % saved | -$15,000 |
| **Estimated total** | — | — | **~$40,000** |

This is the elephant in the room. Mitigation:

- Run **GAIA Level 1 only** (~146 questions instead of 466) for the
  main result; report Level 2/3 as "future work" or a small
  ablation. Cuts GAIA cost ~70 %.
- Run **2 seeds instead of 3** for cells where seed 1 and 2 already
  agree to within 1 pt.
- **Apply for academic compute credits** (OpenAI Researcher Access,
  Anthropic for Researchers, Together AI compute grants).
- **Run cheap models locally** (Qwen via vLLM on a single GPU,
  Step 3.5 Flash via OpenRouter free tier).

Realistic budget after all mitigations: **~$8–12k**, achievable with
typical academic / industry research support.

### 11.2 Timeline

| Month | Phase | Deliverable |
|-------|-------|-------------|
| 1 (now → June) | Phase A: large catalog ingestion + audit refinement | C_full ~5k skills, embedded; updated SKILL_AUDIT.md |
| 2 (June → July) | Phase B: WCB adapter + GAIA adapter | Single-task end-to-end on both benchmarks |
| 3–4 (July → Sept) | Phase C: 5 × 3 × (60 + 146 GAIA-L1) × 3 grid | Raw results; Pareto plots |
| 5 (Sept → Oct) | Phase D: ablations | All 8 ablations complete |
| 6 (Oct → Nov) | Phase E: paper draft | NeurIPS 2027 submission (if not 2026) |

The NeurIPS 2026 D&B deadline (June) is **infeasible** at this start
date; ICLR 2027 (Sept '26) is realistic; NeurIPS 2027 (June '27) is
comfortable.

---

## 12. What's explicitly out of scope

To pre-empt reviewer scope creep:

- **Online skill authoring.** Catalog C_full is fixed at experiment
  start (per skills.sh API call snapshot). Section 7 "future work"
  flags this.
- **Beating absolute SOTA on the main WildClawBench leaderboard.**
  We compete on Personal OpenClaw, not on the frontier-model
  leaderboard.
- **Multi-agent coordination *within* a benchmark task.** OpenClaw is
  single-agent; our coalition is over *skills*, not over runtime
  agents. (Important framing point — the hackathon project muddled
  this; the paper makes it clean.)
- **Training / fine-tuning the base model.** Black-box only.
- **Real-time benchmark execution (streaming).** Batch evaluation
  per WCB / GAIA harness.

---

## 13. Files this proposal touches

| File | What it is |
|------|------------|
| `docs/RESEARCH_PROPOSAL.md` (this file) | The *why* and *what* — paper-shaped framing, contributions, hypotheses, venues. |
| [docs/RESEARCH_PLAN.md](RESEARCH_PLAN.md) | The *how* and *when* — phases, sub-tasks, dependencies. |
| [docs/SKILL_AUDIT.md](SKILL_AUDIT.md) | The Phase A audit — informs §5.1 catalog construction. |
| [docs/MATCHING_PIPELINE.md](MATCHING_PIPELINE.md) | The mechanism's mathematical guts. |
| [docs/GAME_THEORY_PRIMER.md](../GAME_THEORY_PRIMER.md) | The closed-form Shapley derivation. |
| [data/audit/skills_x_wildclaw.csv](../data/audit/skills_x_wildclaw.csv) | The hand-tagged human prior used for the C_curated_50 ablation. |

---

## 14. Next concrete actions

1. **Apply for skills.sh API key** (email mentioned on their docs page).
2. **Start GitHub `path:SKILL.md` crawl** in parallel — this works
   without any external API.
3. **Refactor RESEARCH_PLAN.md** to align Phase A with §5.1 (large
   catalog, not the 50-skill version).
4. **Apply for OpenAI Researcher Access** and Anthropic for
   Researchers credits. Both have rolling deadlines.
5. **Run a *single* WildClawBench task end-to-end** on a cheap model
   to confirm the harness works on local Docker (Phase B1). This is
   the next coding action.

# Skills.sh × WildClawBench audit

**Date:** 2026-05-06.
**Scope:** Phase A of [RESEARCH_PLAN.md](RESEARCH_PLAN.md) — assess
whether the [skills.sh](https://skills.sh/) catalog is a useful source of
skills for the [WildClawBench](https://internlm.github.io/WildClawBench/)
benchmark before committing to ingestion / re-embedding work.

**TL;DR.** Skills.sh is a **partial** catalog for WildClawBench, not a
comprehensive one. We recommend **not** ingesting the full catalog
indiscriminately. Instead, curate ~30–50 skills.sh entries plus
WildClawBench's own task-shipped skills. The mechanism we propose
(Shapley-weighted coalition picker) is *more* defensible against this
backdrop: the gain comes from picking the right 5–10 skills out of a
mixed catalog, not from having a huge catalog.

---

## 1. Why even ask the question

The pre-pivot TODO assumed skills.sh would give us *"150 real entries"*
for the catalog. Two things changed that:

1. The skills.sh JSON API **now requires authentication**
   (`Authorization: Bearer sk_live_…`). Their docs page claims unauth
   works with stricter rate limits, but the live endpoint returns
   `HTTP 401` with no token. API keys are issued on request.
2. Even if we had bulk access, *"more skills"* is not obviously the
   right primitive for WildClawBench. The benchmark grades end-to-end
   tasks (60 of them) inside an OpenClaw container; the relevant
   primitive is **the bundle of skills installed in the lobster
   workspace**, not the catalog size.

So the audit pivot: **fingerprint what kinds of skills exist on
skills.sh, then check which kinds WildClawBench actually rewards.**

## 2. Catalog snapshot

We harvested **189 skill paths** from the `skills.sh` homepage HTML
(unauthenticated, no API). Skills are namespaced as
`/{owner}/{collection}/{slug}` and map 1-to-1 to GitHub repos containing
a `SKILL.md` file (Anthropic-style YAML-frontmatter format).

Raw lists:

- [data/audit/skills_sh_paths.txt](../data/audit/skills_sh_paths.txt)
  — 189 paths.
- [data/audit/owners_histogram.txt](../data/audit/owners_histogram.txt)
  — 40 unique owners.
- [data/audit/collections_histogram.txt](../data/audit/collections_histogram.txt)
  — 46 unique collections.

Top owners by skill count:

| Owner            | Skills | Notes                                         |
|------------------|-------:|-----------------------------------------------|
| coreyhaines31    | 24     | All marketing / SEO / CRO. ~irrelevant for WCB. |
| microsoft        | 20     | Almost all Azure cloud-ops. Irrelevant.       |
| anthropics       | 18     | The high-quality core (pdf/docx/pptx/xlsx).   |
| pbakaus          | 15     | Visual-taste design iteration ("impeccable"). |
| obra             | 14     | Coding practices + agent meta-workflows.      |
| mattpocock       | 12     | TypeScript / dev practice.                    |
| firebase         | 11     | Firebase cloud-ops. Irrelevant.               |
| larksuite        |  6     | Lark = Chinese Slack. Maps to Social Interaction. |
| firecrawl        |  7     | Web scraping cluster. **Sweet spot for SR.**  |
| google-labs-code |  5     | "Stitch" design tooling.                       |

(Full histogram in `data/audit/owners_histogram.txt`.)

The catalog is heavily **dev-tool-skewed**. Roughly:

- **~40 %** dev / coding / cloud-ops (web frameworks, Azure, Firebase).
- **~25 %** marketing / SEO / design (Corey Haines + various boutique
  agencies).
- **~15 %** Anthropic-style document/format tooling and creative
  iteration.
- **~10 %** web scraping / browser automation (Firecrawl + Browser-Use).
- **~5 %**  agent-authoring meta-skills (`skill-creator`, `find-skills`,
  `mcp-builder`).
- **<5 %**  multimodal (image / video / audio).

## 3. Coverage map: skills.sh × WildClawBench categories

We hand-tagged each of the 189 skills with a relevance score against
each of the 6 WildClawBench categories. Scores: 0 = no, 1 = adjacent,
2 = direct match. Full mapping in
[data/audit/skills_x_wildclaw.csv](../data/audit/skills_x_wildclaw.csv).

| WCB category          | N tasks | R≥1 skills | R=2 (direct) | Notable hits                                   |
|-----------------------|--------:|-----------:|-------------:|------------------------------------------------|
| Productivity Flow     | 10      | 7          | 5            | `pdf`, `docx`, `pptx`, `xlsx`, `paper-context-resolver` |
| Code Intelligence     | 12      | 32         | 4            | `tdd`, `systematic-debugging`, `playwright`, `improve-codebase-architecture` |
| Social Interaction    |  6      | 7          | 1            | `lark-approval`, `internal-comms`, `cold-email` |
| Search & Retrieval    | 11      | 11         | 10           | Whole `firecrawl-*` cluster, `browser-use`, `agent-browser` |
| Creative Synthesis    | 11      | 29         | 4            | `gpt-image-2`, `ai-video-generation`, `remotion-best-practices`, `heygen-com` |
| Safety Alignment      | 10      | **0**      | **0**        | *No matches in the public catalog.*           |
| (none / off-topic)    | —       | 0          | 0            | 71 skills (mostly Azure & marketing)           |

### Key findings

1. **Search & Retrieval is the clearest win.** 10 of 11 SR tasks have a
   directly matching skill (the Firecrawl cluster). If our mechanism
   helps anywhere, this is where the signal will be strongest.
2. **Productivity Flow has 5 high-value document-format skills**
   (`pdf`/`docx`/`pptx`/`xlsx`/`typeset`) that cover most of the
   PDF-classify, Wikipedia, and LaTeX-extraction tasks.
3. **Code Intelligence is broad but shallow.** 32 adjacent skills, but
   only 4 directly match — most are React/Next.js/TypeScript flavour,
   while WCB's CI tasks include *SAM3 inference from source* and
   *visual puzzle solving*. There's no computer-vision or
   model-internals skill.
4. **Creative Synthesis has 29 adjacent design skills, but only 4
   actually relate to video / image generation** — the rest are web-UI
   design under "creative". The dominant WCB CS tasks (football match
   clipping, video dubbing, paper-to-poster) need **video editing**
   and **layout** primitives that the catalog mostly lacks.
5. **Safety Alignment is a hole.** Zero skills.sh entries map to
   prompt-injection defense, leaked-API-key detection, or
   malicious-skill-injection. WildClawBench's 10 SA tasks are
   adversarial-grading: skill choice probably **can't help** here, and
   our mechanism should learn to pick the *minimal* skill bundle (or
   none) for SA tasks.
6. **38 % of the catalog is dead weight** for this benchmark
   (71/189 skills with zero relevance — Azure, Firebase, Convex,
   Supabase, Neon, all marketing). Including these in the matcher
   pool just adds noise to the embedding index.

## 4. Implications for the research plan

### 4.1 Catalog construction (revised)

Instead of "ingest skills.sh wholesale", build a **curated catalog of
~50 skills**:

| Source                                      | Count | Rationale                                     |
|---------------------------------------------|------:|-----------------------------------------------|
| Skills.sh R=2 (direct hits)                 | ~24   | High-confidence matches per the mapping CSV.  |
| Skills.sh R=1 high-value adjacency          | ~15   | E.g. `tdd`, `systematic-debugging`, `lark-*`. |
| WildClawBench task-shipped skills           | ~9    | `WildClawBench/skills/{03_task1..6, agent-browser, video-frames, self-improving-agent-3.0.5}`. These are the benchmark's own ground-truth bundles. |
| Bespoke skills we author for SA category   | 3–5   | Static-analysis / secret-scanner / refusal-pattern checker. The catalog has none. |

Total: **~50–55 skills**. This fits comfortably in the existing
`skills` Mongo collection, single re-embedding run is <$0.10 with
`text-embedding-3-small`, and the matcher's top-K@cosine is meaningful
because the index contains few decoys.

### 4.2 Hypotheses to test in Phase C

The audit also sharpens the experimental hypotheses:

- **H1 (strong).** Coalition picker beats `topK-similarity` on
  **Search & Retrieval** (10 directly-matching skills, picker has to
  choose ≤3 — clear pruning task).
- **H2 (strong).** Coalition picker beats `all-skills` on
  **Productivity Flow** because installing all 24 R=2 skills creates
  prompt-budget pressure, while the right 3–5 suffice.
- **H3 (moderate).** No mechanism beats `vanilla` on **Safety
  Alignment**. Skill choice is dominated by the model's refusal
  heuristic, and the catalog has no relevant skills anyway. Report
  this as a limitation, not a failure.
- **H4 (weak).** Cross-model gain is larger on cheap models (e.g.
  Step 3.5 Flash). Cheap models benefit more from a curated skill
  bundle because they have less internal knowledge to compensate.

### 4.3 What this changes in `RESEARCH_PLAN.md`

- **Phase A.** Drop A1 (full skills.sh API ingestion) — replace with
  the 50-skill curated catalog above. *(Done — this audit replaces
  it.)*
- **Phase A4.** Re-embedding now small enough to be a 1-line script
  rather than a separate task.
- **Phase B.** WildClawBench adapter unchanged.
- **Phase C.** Refocus the experiment on the 4 categories where
  signal is plausible (PF, CI, SI, SR + half of CS). Treat SA as a
  control category that we **expect** the mechanism not to help on.
- **Phase D.** Add a new ablation: catalog-size sensitivity. Run
  Phase C with 25 / 50 / 100 / 189 skills in the index.

## 5. Open questions

1. **SKILL.md content** — we have slugs but not full SKILL.md text
   yet. Need it before we can re-embed (descriptions drive the
   embedding). For the curated 50, that's 50 GitHub fetches; trivial.
2. **Authoritative skills.sh API key.** Do we ask for one anyway?
   Even with a curated catalog, the API exposes `installs` counts
   that would fuel the `topK-popularity` baseline. *Probably yes —
   non-blocking and free.*
3. **Per-category reputation cold start** (already in
   RESEARCH_PLAN §3.1) — the audit confirms this matters: a skill
   that helps on SR tasks may be useless on PF, so reputation must be
   indexed by `(skill, wcb_category)` not by skill alone.
4. **Token-budget ceiling** (RESEARCH_PLAN §3.2) — needs an OpenClaw
   smoke-test once we author the curated 50. Each SKILL.md adds
   ~500–2000 tokens to the system prompt.

## 6. Files produced by this audit

| Path                                         | Content                                          |
|----------------------------------------------|--------------------------------------------------|
| [data/audit/skills_sh_paths.txt](../data/audit/skills_sh_paths.txt)             | 189 raw `/{owner}/{collection}/{slug}` paths.    |
| [data/audit/owners_histogram.txt](../data/audit/owners_histogram.txt)            | Skills-per-owner counts.                         |
| [data/audit/collections_histogram.txt](../data/audit/collections_histogram.txt) | Skills-per-collection counts.                    |
| [data/audit/skills_x_wildclaw.csv](../data/audit/skills_x_wildclaw.csv)         | Hand-tagged mapping `slug → bucket → wcb_category → relevance`. |
| [docs/SKILL_AUDIT.md](SKILL_AUDIT.md)                                           | This report.                                     |

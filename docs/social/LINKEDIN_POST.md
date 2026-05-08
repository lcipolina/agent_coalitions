# Cadre — LinkedIn post + carousel

**Audience:** ML researchers, agent-framework practitioners, and the
broader ML / engineering crowd that uses LinkedIn for technical
discovery (heavier on European researchers and senior engineers than
Twitter).
**Tone:** researcher-engineer. Plain, paragraphed, no emoji storms.
LinkedIn rewards clarity and substance; it punishes hype.

**Author handle:** `@LuciaCKun` (X) — link from LinkedIn back to your
X handle if your LinkedIn profile carries it.

**Posting tips**
- Schedule for **Tuesday or Wednesday, 08:30–10:00 your local time** —
  highest engagement window for the technical-LinkedIn crowd.
- Post the long-form text **with the carousel attached as a single
  PDF**. Native carousels outperform image attachments by a wide
  margin.
- Reply to the first 5–10 comments in the first hour. The algorithm
  scores early-comment velocity heavily.
- Do not edit the post in the first 24 h after publishing — edits
  reset the algorithmic boost.

---

## The long-form post (≈1100 chars; safely under the 3000 cap)

The first 210 characters are the only ones that show before the
"…see more" fold. Treat them as a standalone hook.

> Most agent frameworks try to build one giant agent that does
> everything. We tried treating it as team formation over a
> marketplace of 100,000 specialists.
>
> Cadre splits a complex prompt into subtasks, then hires a small
> team of specialists for each one from a vector-indexed skill
> catalog. Each team has its own marshal and its own raison d'être —
> one for structure, one for design, one for cost. Inside a team,
> agents collaborate; teams don't talk across.
>
> The matching pipeline is small and explicit:
>
> 1. find candidates by meaning (cosine similarity in the catalog);
> 2. filter by fit (drop matches below a coverage threshold);
> 3. pick the smallest team that covers all required capabilities
>    (set cover).
>
> After the run, Shapley values measure each agent's marginal
> contribution. Good performers gain reputation; future runs prefer
> them. That's the only piece of cross-run state — and it's what
> lets the system *learn who's actually good* over time.
>
> Behind the demo, a paper-shaped methodology aimed at
> NeurIPS / ICLR: skill-bundle selection framed as a coalition
> formation problem, evaluated on WildClawBench and GAIA, with
> closed-form Shapley as the picker.
>
> 6-slide carousel below explains the methodology end-to-end.
>
> 🔗 Live demo: https://agentcoalitions.streamlit.app
> 📄 Code: github.com/lcipolina/agent_coalitions
> 📄 Research proposal: github.com/lcipolina/agent_coalitions/blob/master/docs/RESEARCH_PROPOSAL.md
>
> Curious what you would change about the team-formation step or the
> credit-assignment rule — replies welcome.
>
> #AIAgents #MultiAgentSystems #GameTheory #LLMs #ResearchEngineering

**Why the closing CTA is specific.** Asking for opinions on the
*team-formation step or the credit-assignment rule* invites
substantive replies from people who actually work on this; "thoughts?"
gets you "cool!" and nothing usable.

**Why three URLs and not one.** LinkedIn links don't appear as cards
when there are multiple in a post — that's actually fine here, because
LinkedIn's algorithm down-ranks posts that try to send users away.
Three plain-text URLs feel like *references*, not a redirect, and
that's how LinkedIn treats them.

---

## The PDF carousel — 6 slides

**Format:** export as a single PDF (LinkedIn calls these "documents").
Aspect ratio **1:1 (1080 × 1080)** or **4:5 (1080 × 1350)** — both
display cleanly on mobile. Do not use 16:9; it gets letterboxed.

**Tool:** Keynote or Google Slides → File → Export → PDF.
Single-page-per-slide, no animations.

**Typography:** sans-serif, 24 pt minimum body text, 56 pt headers,
high contrast. Slide must be legible on a phone in bright sunlight.

**No animation, no transitions.** PDFs don't animate.

---

### Slide 1 — Title

**Header:** Cadre

**Body (one line):** A team of specialized agents for tasks too
complex for a single agent.

**Footer (small):** [agentcoalitions.streamlit.app](https://agentcoalitions.streamlit.app)
· github.com/lcipolina/agent_coalitions

**Visual:** clean, mostly white, just the title and the URL. Sets the
calm researcher tone — *not* a startup pitch deck.

---

### Slide 2 — The problem

**Header:** One giant agent vs. a team of specialists

**Layout:** two-column, side-by-side comparison.

**Left column — "Single agent":**
- One model, every task
- One context window for everything
- Hard to attribute success/failure
- Hard to specialize

**Right column — "Cadre":**
- Many specialists, small teams
- Each team focused on one subtask
- Shapley values attribute credit
- Reputation persists across runs

**Visual hint:** left column greyed-out / muted; right column in your
brand colour. The visual contrast does most of the work.

---

### Slide 3 — The methodology, end to end

**Header:** How it works

**Visual:** the methodology diagram from the demo's
**Methodology** tab, exported as PNG, full-bleed on the slide.

**Footer (small):** Orchestrator → marshals → agents · marketplace
of 100,000 vector-indexed skills · set-cover for team formation.

**How to capture the diagram:** in the running app on the Methodology
tab, right-click the Graphviz diagram → *Save image as…* (Streamlit's
graphviz_chart renders to SVG, but most browsers offer a PNG export).
If your browser doesn't, take a clean screenshot at 2× zoom.

---

### Slide 4 — The marketplace

**Header:** A marketplace of 100,000 specialists

**Body (3 short bullets):**

- Skills are vector-indexed by capability
- For each subtask: find candidates by meaning, filter by fit, pick
  the smallest team that covers everything
- The team is the smallest set whose skills cover the subtask's
  required capabilities

**Visual:** zoom on the green cylinder + the three friendly mechanism
boxes from the methodology diagram.

---

### Slide 5 — The team hierarchy

**Header:** Each team has its own raison d'être

**Body:** crop of the right column of the methodology diagram showing
Marshal T1 / T2 / T3 with their three agents each. Caption underneath:

> Three teams, one marshal each, three agents per team. Each agent
> contributes one skill. Inside the team, agents talk to each
> other; teams don't talk across.

---

### Slide 6 — Cross-run learning + CTA

**Header:** The system remembers who pulled their weight

**Body:**

- After each run, Shapley values measure each agent's marginal
  contribution
- Reputations update on a per-skill basis
- Future runs prefer agents with higher reputation in the relevant
  skills
- This is the only piece of cross-run state

**Footer / CTA:**

- Live demo · agentcoalitions.streamlit.app
- Code · github.com/lcipolina/agent_coalitions
- Research direction · NeurIPS / ICLR target, see RESEARCH_PROPOSAL.md
- Replies welcome on team formation and credit assignment.

---

## Out-of-scope (deliberately not in the post or carousel)

- Database vendor name — "vector-indexed catalog" / "the database"
  only.
- Hackathon context — framed as a research-engineering project.
- Any "follow for more" or growth-hack language.
- Specific model names / costs / vendor logos.
- The OSS-vs-API research direction — out of scope for the launch
  post; save for an eventual preprint announcement.

---

## After-launch checklist

- [ ] Pin the post to your LinkedIn profile for 7 days.
- [ ] Cross-post a link to it on X with a one-line teaser ("Long-form
      writeup of Cadre is on LinkedIn — link in reply").
- [ ] If the post crosses 50 reactions in 24 h, reply to it with a
      follow-up document or thread (any of: the WildClawBench
      experiment, the closed-form Shapley derivation, the 100k-skill
      catalog audit). Keeps the algorithmic boost going.

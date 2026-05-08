# Cadre — X / Twitter thread

**Audience:** ML researchers, agent-framework practitioners, builders.
**Tone:** researcher-engineer. No hype, no "follow for more", no emoji-spam.
Focus on the mechanism and the empirical claim.

**Author handle:** `@LuciaCKun`

**Posting tips**
- Schedule for **Tuesday or Wednesday, 09:00–11:00 your local time** —
  highest engagement window for the technical-Twitter timezone.
- Post the whole thread at once (not over hours). The algorithm
  rewards in-thread dwell time.
- Reply to your own thread with extra context as comments come in,
  rather than editing tweets.
- Pin the first tweet to your profile after posting.

---

## Asset checklist (capture before posting)

You will need 6 screenshots and 1 short screen recording. All from the
live app at https://agentcoalitions.streamlit.app — never from a
local-only run, so the URL in screenshots is the deployed one.

Run the demo with the **bridge** prompt (default). Use a clean
browser window, no extensions, light theme.

| ID | What | Where in the app | Notes |
|----|------|------------------|-------|
| `IMG-1` | The methodology hero diagram | **Methodology** tab | Crop to just the Graphviz diagram + the title strip "Cadre — A team of specialized agents…". This is the **single most important asset**. |
| `IMG-2` | The four numbered cards | **Methodology** tab, below the diagram | Crop to just the 4 columns (Split / Hire / Each team / Learn). |
| `IMG-3` | Teams tab | **Teams** tab | Show 3 teams with their assigned skills. |
| `IMG-4` | Agent comms | **Agent comms** tab | Pick a team with at least 2 messages exchanged. |
| `IMG-5` | MongoDB architecture diagram | **MongoDB** tab | The diagram only, not the explanatory paragraphs. |
| `IMG-6` | Reputation tab | **Reputation** tab | Show both per-run deltas and cumulative reputation. |
| `VID-1` | 20–30 s screen recording | full app run, start to finish | See storyboard below. |

---

## Tweet 1 — hook + hero image (IMG-1)

> Most agent frameworks try to build one giant agent that does everything.
>
> We tried treating it as team formation over a marketplace of 100,000 specialists.
>
> Here's how Cadre works ↓

**Asset:** `IMG-1`
**Char count:** ~210 (room to spare; do not exceed 250 to keep the
"see more" fold safe).

**Why this hook:** sets the contrast in one sentence (giant agent vs.
marketplace), commits to a number (100k) that's specific enough to
sound real, and ends with the canonical thread cue (`↓`). No emoji
storm, no question marks, no "🧵 1/8" header — those signal "marketing
thread" and ML-Twitter scrolls past.

---

## Tweet 2 — what each team does (IMG-3)

> One marshal per team, three agents underneath. Each agent
> contributes a single skill from the catalog.
>
> Teams have a *raison d'être* — one for structure, one for
> design, one for cost. Inside the team, agents talk to each other.
> Teams don't talk across.

**Asset:** `IMG-3` (Teams tab screenshot)

---

## Tweet 3 — the matching pipeline

> The marketplace is vector-indexed by capability. For each subtask:
>
> 1. find candidates by meaning (cosine similarity)
> 2. filter by fit (drop low-score matches)
> 3. pick the smallest team that covers everything (set cover)
>
> The team is the smallest set that covers the subtask's required skills.

**Asset:** none (text-only tweet — gives the reader a pause between
visual tweets and is the place to drop technical keywords for search).

---

## Tweet 4 — the run, in motion (VID-1)

> Live run on the deployed demo. Decompose → match → team
> collaboration → synthesise → validate → cost → report.
>
> Every artefact persisted; every step replayable from the database
> alone.

**Asset:** `VID-1` (see storyboard below)

---

## Tweet 5 — agents communicating (IMG-4)

> Inside a team, agents take turns. Marshal kicks off, agents
> contribute their domain output, marshal reconciles. Every message
> indexed by (run, subtask, timestamp).

**Asset:** `IMG-4`

---

## Tweet 6 — what the database does (IMG-5)

> Five jobs, one database:
>
> ① the catalog
> ② the vector index
> ③ the team message bus
> ④ the audit / replay log
> ⑤ cross-run reputation memory
>
> The Python pipeline is stateless. Every line of state is in one of
> those five places.

**Asset:** `IMG-5`

---

## Tweet 7 — credit assignment (IMG-6)

> After each run, Shapley values measure each agent's marginal
> contribution. Reputations update and carry to the next run.
>
> This is the only piece of cross-run state — and it's what lets the
> system *learn who's actually good* over time.

**Asset:** `IMG-6`

---

## Tweet 8 — the research framing + CTA

> Behind the demo: a paper-shaped methodology aimed at NeurIPS / ICLR.
> Skill-bundle selection as coalition formation, evaluated on
> WildClawBench + GAIA, with closed-form Shapley as the picker.
>
> Demo · https://agentcoalitions.streamlit.app
> Code · github.com/lcipolina/agent_coalitions
> Proposal · github.com/lcipolina/agent_coalitions/blob/master/docs/RESEARCH_PROPOSAL.md
>
> Curious what you'd change about the team-formation step — replies welcome.

**Asset:** none.

**Note on the CTA:** the closing line invites engagement on a *specific*
technical question rather than a generic "thoughts?". Specific
prompts get specific replies — and specific replies are what algorithm
weight is based on.

---

## VID-1 — 30-second screen recording storyboard

**Tool:** QuickTime Player → File → New Screen Recording.
Trim to 28 seconds in QuickTime's built-in trimmer (Edit → Trim).
Export at 1080p (the default).

**No audio.** Twitter autoplays muted. Add on-screen text overlays
in QuickTime (or Keynote → export to video) so the message lands
without sound.

**Pre-flight:**
1. Open https://agentcoalitions.streamlit.app in a clean browser window.
2. Resize the window to 16:9 (e.g. 1600 × 900). Avoid full-screen — the
   browser chrome makes it obvious it's a real running app, which
   builds trust.
3. Hide bookmarks bar, close other tabs.
4. Have the prompt dropdown set to "Design a bridge for 50 cars per
   hour — modern design".
5. Pre-position the page at the top.

**Shot list (28 s total):**

| t | Duration | Shot | On-screen text overlay |
|---|---:|------|------------------------|
| 0 s | 3 s | Static on the title strip ("Cadre — A team of specialized agents…") and the prompt dropdown | "From a single prompt…" |
| 3 s | 2 s | Cursor moves to **Run pipeline** button, click | (no overlay — let the click sell itself) |
| 5 s | 6 s | Live progress: progress bar advancing, subtask chips appearing, agent matches scrolling | "…the orchestrator splits the work, hires teams from a 100k-skill marketplace…" |
| 11 s | 2 s | Quick switch to **Teams** tab | "Three teams. One marshal each." |
| 13 s | 3 s | Pan over the three colored team blocks | "Each agent brings one skill." |
| 16 s | 2 s | Switch to **Agent comms** tab | "Agents collaborate inside the team." |
| 18 s | 3 s | Scroll through 2–3 messages | (let it read; no overlay) |
| 21 s | 2 s | Switch to **Reputation** tab | "Shapley values measure who contributed." |
| 23 s | 3 s | Show the reputation deltas | "Reputations carry to the next run." |
| 26 s | 2 s | End card — Cadre title + URL | "agentcoalitions.streamlit.app" |

**Pacing rule:** every clip is at least 2 s — anything shorter is
imperceptible at 1080p with autoplay. Total cuts: 9. That's fast but
not flickery.

**Easy version (no overlays, 20 seconds):** if QuickTime overlays are
fiddly, just record the screen, trim to 20 s, post as-is. The
diagrams in IMG-1 carry the explanation; the video is just *proof
that the thing runs*.

---

## Out-of-scope (deliberately not in the thread)

- Database vendor name — referred to as "the database" only.
- Hackathon context — this is a research-engineering project, not a
  hackathon submission, in the social framing.
- Any "follow for more" / growth-hack language.
- Cost / model details — saved for replies if anyone asks.
- The OSS-vs-API research direction — out of scope for the demo
  thread, save for the eventual paper / preprint announcement.

# Presenting Agent — future idea

> **Status:** parked. Not for the hackathon demo. Captured here so we don't
> lose the idea after the credits expire.

Lucia has free credits on **ElevenLabs** (TTS + Conversational Agents).
The thought: have an AI voice deliver the pitch instead of (or alongside)
a human presenter. This document is the brain-dump so a future weekend
project can pick it up.

## 1. Three implementation tiers

| Tier | What | Effort | Risk | When to use |
| --- | --- | --- | --- | --- |
| **A. Pre-recorded narration** | Paste `docs/PITCH.md` into ElevenLabs Studio, generate MP3, play on demo day. | ~10 min | Very low. Just an audio file. | Backup if presenter loses voice. Demo videos. |
| **B. Hybrid (intro/outro voiced, live driver in middle)** | 30-second AI-voiced intro hook + closer, presenter drives the live demo. | ~20 min | Low. Voice is fully pre-recorded. | When you want a memorable opener without giving up live presence. |
| **C. Conversational agent (real-time Q&A)** | ElevenLabs Conversational AI agent with `docs/PITCH.md` as the system prompt + knowledge base. Speaks **and listens**. | 30–60 min + tuning | Medium-high. Latency, network, "AI presenting AI" awkwardness. | Standalone kiosk demo. Recorded marketing video. **Not** for live judging. |

## 2. Recommended voice / settings (ElevenLabs Studio)

- **Voices to try first:** Rachel (warm, clear), Adam (neutral male), Charlie (younger, energetic). Avoid the over-acted "narrator" presets.
- **Stability:** 45–55 (lower = more expressive, higher = more consistent).
- **Clarity / Similarity boost:** 70–80.
- **Speaker speed:** 0.95–1.0 (1.05 if the pitch runs long).
- **Model:** `eleven_turbo_v2_5` for fastest generation; `eleven_multilingual_v2` if any non-English content.

## 3. Script preparation (for Tier A / B)

The single source of truth for the pitch is [docs/PITCH.md](PITCH.md).
Before pasting into Studio:

1. Strip stage directions in square brackets: `[gesture to screen]`,
   `[click Run]`. The voice agent will read them verbatim otherwise.
2. Replace inline code (`gpt-4o-mini`) with spoken form
   ("GPT four-oh mini").
3. Spell out symbols: `~$0.05` → "around five cents".
4. Add SSML breaks at natural pauses:

   ```xml
   <break time="500ms"/>
   ```

5. Split into **5 separate clips of ~60 seconds each** (one per
   pitch section). Easier to:
   - re-generate just one section if a phrase sounds wrong;
   - pause between sections and click through the demo;
   - swap order if the demo flow changes.

## 4. Conversational agent (Tier C) recipe

If we ever do this for a kiosk / video:

1. **Create agent** in ElevenLabs Conversational AI dashboard.
2. **System prompt:** paste the elevator pitch + Q&A cheat-sheet from
   [docs/PITCH.md](PITCH.md).
3. **Knowledge base:** upload `docs/MVP_DESIGN.md`,
   `docs/ARCHITECTURE.md`, `docs/MATCHING_PIPELINE.md`,
   `docs/GAME_THEORY_PRIMER.md`. The agent will RAG over them when
   answering off-script questions.
4. **Tools:** none — the agent should only **describe** the system,
   not control it. Manual demo driver still clicks buttons.
5. **Voice:** same recommendations as §2.
6. **Guard rails:** add a system prompt line *"If asked about anything
   outside the Agent Coalitions project, politely redirect back to the
   demo."*

## 5. Why this is parked, not done

- Demo day is in 4 hours. Introducing a new live system is a foot-gun.
- The presenter speaks fluent English and knows the system end-to-end —
  audience engagement still wins over TTS, even good TTS.
- The hackathon Wi-Fi already had DNS issues today. Adding a real-time
  voice agent that needs reliable websocket egress is asking for a
  failure mode.
- Best case for a voice agent is the **post-hackathon recorded demo
  video** for LinkedIn / portfolio, where retakes are free.

## 6. Reusing this for the demo video later

Recipe for a 5-minute demo-video voice-over:

1. Record screen with QuickTime (or OBS) running the full pipeline in
   mock mode (deterministic, fast, repeatable).
2. Generate Tier A narration (5 × 60-second clips) from
   `docs/PITCH.md`.
3. Edit in iMovie / Resolve: align each clip to the matching screen
   moment.
4. Add 2–3 seconds of soft music under the audio (royalty-free).
5. Export 1080p, upload to YouTube unlisted, share with judges and on
   LinkedIn.

Total time budget: ~2–3 hours for a polished video.

## 7. Cost notes

- ElevenLabs Studio is a fixed per-character cost. The full pitch
  (~750 words, ~4500 chars) costs ~50% of a Starter month's quota.
  Keep clips short.
- Conversational AI bills per minute of conversation **and** per
  character of TTS. For a 5-minute demo with judge Q&A, budget
  ~30 minutes of agent time.

---

**Owner:** Lucia. Revisit when:
- (a) the credits are about to expire,
- (b) we need a recorded demo video for an application / portfolio, or
- (c) the project gets accepted somewhere that wants a kiosk demo.

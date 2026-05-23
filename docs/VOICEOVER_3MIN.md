# llmai — 3-Minute Voiceover Script

A longer-form explainer, suitable for a tutorial intro, conference lightning
talk, or "explained" YouTube video. Pairs with [`website/promo.html`](../website/promo.html)
as B-roll if you don't have time to stage a real demo.

**Format:** ~440 words at conversational pace (≈145 wpm = 3:00 flat).
**Tone:** calm, technical, a touch dry. Don't oversell.
**Direction notes:** `[ ]` = delivery cues, `▌` = hard scene cuts, `…` = brief
breath, **bold** = stress word.

---

## ▌ 0:00 – 0:25 · Hook & problem

[Steady, slightly low. No music, or barely any.]

> Imagine you ask an AI to fix a bug in your code. It reads three files.
> It writes a patch. It runs your tests. … And every byte of that —
> your source, your prompts, your terminal history — gets uploaded to a
> server you don't control. [beat] That's the default for almost every
> AI coding tool right now.
>
> **llmai** is an alternative.

*On-screen:* hero shot of the llmai logo · tagline fades in.

---

## ▌ 0:25 – 0:50 · What it is

[Warmer, a touch more energy.]

> llmai is an **open-source** AI coding agent that runs **entirely on
> your laptop**. It's powered by Ollama, so the model — whether that's
> Qwen, Llama, Gemma, Phi, or Mistral — sits on your machine, not
> someone else's. No API keys. No telemetry. No usage caps. You install
> it with three commands, and it just works.

*On-screen:* terminal — `pip install -e .` → `ollama serve` → `llmai-server`.

---

## ▌ 0:50 – 1:30 · The agent loop

[Steady, explanatory. This is the "how" section — slow down a little.]

> What makes it an **agent**, not a chatbot, is the loop. When you give
> it a task, it doesn't reply once and stop. It plans the next step.
> Calls a tool — maybe reading a file, maybe running a shell command.
> Looks at the result. Plans again. Up to twenty iterations until the
> task is done.
>
> There are six built-in tools: read, write, edit, list, search, and
> run command. Reads happen instantly. Anything that mutates state —
> writing files, executing shell commands — **pauses for your approval**.
> You see exactly what it wants to do before it happens.

*On-screen:* diagram of the loop · tool cards animating in sequence · a
permission card with Allow/Deny visible.

---

## ▌ 1:30 – 2:15 · Integrations & the money shot

[Pick up energy here — this is the demo.]

> On top of that local foundation, llmai integrates with **GitLab**.
> Set one environment variable and the agent gets eleven extra tools —
> for triaging issues, fetching merge requests, reading failing pipeline
> logs, posting comments, opening fix MRs.
>
> The combination is what makes it real. You say: *"the pipeline on MR
> forty-two is red — figure out what broke and open a fix."* The agent
> reads the merge request, pulls the failing job log, finds the
> assertion that failed, edits the source file, asks for your approval,
> commits, pushes, opens a follow-up MR. [beat] Eight tools chained from
> a single sentence. Every state-changing step still goes through you.

*On-screen:* live demo from `promo.html` — tool cards cascading, permission
card auto-approving, "Fix MR !43 opened ✓" at the end.

---

## ▌ 2:15 – 2:40 · Model flexibility

[Settle back. Technical clarification beat.]

> Want a stronger model than what fits on your laptop? Set
> `GEMINI_API_KEY` and the same agent runs against **Google Gemini** —
> 2.5 Pro, 2.5 Flash, whichever you choose. The architecture is
> provider-agnostic; the same client speaks to Ollama, to Gemini through
> AI Studio, and to Vertex AI through its OpenAI-compatible endpoint.
> Switch by setting an environment variable.

*On-screen:* startup banner cycling through `Provider: Ollama (local)` →
`Provider: Google Gemini` to show the swap.

---

## ▌ 2:40 – 3:00 · Wrap & CTA

[Confident, conclusive. Not pushy.]

> It's path-sandboxed, permission-gated, and MIT licensed. The whole
> thing is a few hundred lines of readable Python — not a framework,
> just a small, honest loop.
>
> If you want an AI coding agent that respects your laptop, your
> privacy, and your time — llmai is on GitHub.
>
> [smiling] Three commands, and it's running.

*On-screen:* `github.com/sechan9999/LLMai` fills the frame · subtitle:
"git clone · ollama serve · llmai".

---

## Recording tips

- **Read each `▌` block as one breath group.** If you have to inhale
  mid-sentence, that block is too long — rewrite, don't push through.
- **Pause on the `[beat]` markers** for ~0.4s. They're where editors cut
  to a different visual.
- **Record at 48 kHz / 24-bit** mono. A USB condenser mic (Yeti, AT2020,
  even a Shure MV7) is plenty.
- **Treat the room before the mic.** A duvet thrown over your head
  beats any plugin.
- **Do three full takes** before listening back. The second take is
  almost always the best one.

## Subtitle/caption file

If you need an SRT, generate one with Descript or YouTube Studio's
auto-caption after you have the audio, then hand-correct technical
terms (`Ollama`, `Vertex AI`, `MR !42`, `qwen2.5-coder`). Auto-caption
mishears all of those at least once.

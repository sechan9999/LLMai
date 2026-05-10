# vixcode — Promo Video Script

A 60-second pitch suitable for a hackathon submission, GitHub README hero, or
social share. Two cuts: a full **60s** version and a **15s** social teaser.

A self-contained animated companion lives at [`website/promo.html`](../website/promo.html).
Open it in the browser, screen-record it, and you have your B-roll without
having to stage a real demo.

---

## Recording workflow (recommended)

1. Open `website/promo.html` in Chrome at 1920×1080. Wait for it to start.
2. Record the screen with **OBS** (free), **ScreenStudio** (Mac, polished),
   or QuickTime → "New Screen Recording". Aim for 1080p, 60fps.
3. Record the voiceover separately into Audacity / GarageBand reading the
   script below. This usually beats live narration for clarity.
4. Cut on the scene boundaries (`▌` in the script). Drop the VO over the
   B-roll. Add subtle motion music (e.g., epidemic sound "Anbr — In Motion").

If you'd rather just narrate live with OBS, the script is tight enough
that one decent take usually works.

---

## 60-second cut

> **Tone:** confident, technical, a touch dry. No marketing puffery.
> Pace ≈ 145 words per minute. Hard cuts on `▌`.

### ▌ 0:00 – 0:05 · Hook

**On screen:** vixcode logo glows in. Tagline appears underneath:
*"An AI coding agent that never leaves your laptop."*

**Voiceover:**
> "Most AI coding agents send every file you open to someone else's GPU."

### ▌ 0:05 – 0:14 · Problem

**On screen:** quick montage — a `curl https://api.openai.com/...` line, a
blurred-out source file being uploaded, a "$0.42" cost meter ticking.

**Voiceover:**
> "Your code, your prompts, your terminal history — all of it leaves the
> machine. That's a privacy problem, a vendor lock-in problem, and at scale,
> a budget problem."

### ▌ 0:14 – 0:24 · Solution intro

**On screen:** terminal types:
```
$ pip install -e .
$ vixcode-server
INFO: Uvicorn running on http://localhost:7777
```
Banner reads: `Provider: Ollama (local) · Model: qwen2.5-coder`.

**Voiceover:**
> "vixcode is an open-source coding agent that runs entirely on your
> hardware via Ollama. No API keys. No telemetry. Same agentic loop you
> expect — read files, edit code, run commands — but every byte stays
> local."

### ▌ 0:24 – 0:42 · Live demo (the money shot)

**On screen:** Web UI opens. User types and hits Enter:

> *"The pipeline on MR !42 is red. Figure out what broke and open a fix MR."*

Tool cards animate in, top to bottom:

```
⚙ gitlab_get_mr(iid=42)            → MR title + diff
⚙ gitlab_list_pipelines(status=failed)
⚙ gitlab_get_job_log(job_id=8814)  → "AssertionError on line 137"
⚙ read_file("tests/test_login.py")
⚙ edit_file("src/auth.py", ...)    → ⚠ Permission required → ✓ Allow
⚙ run_command("git commit -am 'fix: …' && git push")
⚙ gitlab_create_mr(...)            → !43 opened
```

**Voiceover:**
> "Watch this. Failing pipeline on a merge request — the agent reads
> the MR, pulls the failing job log, finds the assertion that broke,
> edits the source, asks me to approve the write, pushes the fix,
> and opens a follow-up MR. Eight tools chained, one prompt."

### ▌ 0:42 – 0:52 · Differentiators

**On screen:** four cards slide in:

| Card | Text |
|---|---|
| 🔒 | 100% local by default · Gemini optional |
| 🔧 | 6 file/shell tools · 11 GitLab tools |
| 🔄 | Native + XML tool-calling — works with Gemma, Phi, Mistral |
| 🛡️ | Path-sandboxed, permission-gated, MIT licensed |

**Voiceover:**
> "Local-first, with Google Gemini as an opt-in backend when you need
> the bigger model. Works with any Ollama model — Qwen, Llama, Gemma,
> Phi, Mistral. Path-sandboxed, permission-gated. MIT licensed."

### ▌ 0:52 – 1:00 · CTA

**On screen:** GitHub URL fills the frame:

```
github.com/sechan9999/LLMai
```

Subtitle: *"git clone. ollama serve. vixcode."*

**Voiceover:**
> "It's three commands to start. Link in the description."

---

## 15-second social cut

> **Use case:** Twitter / LinkedIn / Threads. Drops you straight into the
> demo with no preamble.

### ▌ 0:00 – 0:03

**On screen:** vixcode logo → tagline.
**VO:** "An AI coding agent that runs entirely on your laptop."

### ▌ 0:03 – 0:12

**On screen:** the demo prompt and tool cards (compressed; show 4 of 8).
**VO:** "Failing pipeline → agent reads the log, fixes the code, opens
an MR. All locally."

### ▌ 0:12 – 0:15

**On screen:** GitHub URL.
**VO:** "MIT licensed. Link below."

---

## Asset checklist

- [ ] 1080p screen recording of `website/promo.html` (full 60s loop)
- [ ] Voiceover audio (60s + 15s)
- [ ] Logo PNG (already in landing) — for thumbnail
- [ ] Background music with broadcast license (Epidemic Sound, Artlist, or
      Pixabay royalty-free)
- [ ] Subtitles burned in (auto-generate with Descript or YouTube and
      hand-correct)

## Music suggestions (royalty-free)

- *"In Motion"* — Anbr (Epidemic) — driving but not aggressive
- *"Pixel Push"* — Slynk (Free Music Archive) — synthy, fits dev tooling
- *"Background Score 12"* — Coma-Media (Pixabay) — neutral, free

## Things NOT to say

- Never claim "fastest" / "smartest" / "best" — unverifiable.
- Don't compare directly to Cursor/Copilot/Claude Code by name. Stay on
  your own value prop ("local", "self-hostable", "no telemetry").
- Don't promise tool counts beyond what's shipped.

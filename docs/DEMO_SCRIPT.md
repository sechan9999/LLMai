# LLMai hackathon demo — 3-minute video script (GitLab partner track)

**Target length:** 2 min 45 s, hard cap 3 min
**Format:** Screen recording with voiceover, no talking head
**Tone:** Engineer to engineer — show, don't sell

The pitch for the GitLab track: **a local-first project with a runnable
Gemini 3 + Google ADK investigation profile connected to GitLab's official
MCP server**. The ADK profile is read-only; the separate LLMai Web runtime
contains the interactive write approvals. The three
awareness layers appear as a fast montage, not the main act.

---

## Shot list

### 0:00 – 0:15 · The hook (15 s)

**On screen:** Split: a normal chatbot reply on the left ("Sorry, I don't
have context for that") and LLMai on the right calling
`mcp__gitlab__get_issue` *before* writing code.

**Voiceover:**
> "Every AI coding agent forgets what it did yesterday and ignores what
> your team already learned. LLMai does neither — and your source code
> never leaves your laptop."

### 0:15 – 0:35 · What it is, fast (20 s)

**On screen:** Quick `ls llmai/ google_agent/` showing `agent.py`,
`google_cloud.py`, `permissions.py`, and `mcp/`. Then show the ADK
`root_agent`, Gemini 3 model setting, and official GitLab MCP URL.

**Voiceover:**
> "LLMai is local-first, and this optional profile is built with Google
> Agent Development Kit. Gemini 3 is the orchestrator, with read-only
> workspace tools and GitLab's official MCP server attached directly."

### 0:35 – 0:55 · Startup & MCP discovery (20 s)

**On screen:**
1. `adk web .` — ADK discovers `google_agent`; startup shows the GitLab MCP
   subprocess connecting and tools registering
2. Caption: "GitLab official MCP server · gitlab.com/api/v4/mcp · bridged
   to stdio via mcp-remote"
3. ADK Web opens with **google_agent** selected and Gemini 3 shown in config

**Voiceover:**
> "On startup, Google ADK constructs the LLMai agent and spawns the bridge
> to GitLab's official MCP server,
> runs the MCP handshake, and discovers the tools available to this GitLab
> account. The adapter filters mutation-oriented tool names, leaving this
> demonstration profile read-only."

### 0:55 – 2:05 · The multi-step mission (70 s) ★ THE CORE

**On screen:** ADK Web. Type one read-only prompt:

> *"Check GitLab issue #1 in llmai1/LLMai about the failing login test,
> find any related merge requests or notes, inspect the local
> implementation in workspace/demo-login, and propose a patch plan."*

Capture these five beats (jump-cut the waiting):

1. `mcp__gitlab__get_issue` card → issue text appears (caption: "GitLab
   via MCP — tool call #1")
2. Agent finds the related MR / discussion via a second `mcp__gitlab__*`
   call (caption: "team context, not guesswork")
3. `read_file` on the local repo — auto-approved, read-only
4. Agent identifies the likely file and explains the proposed change
5. Caption: "ADK demo profile is read-only; no file or GitLab mutation tools"

**Voiceover:**
> "One prompt, one investigation. Watch the plan unfold: first, the agent pulls
> the issue from GitLab over MCP. Second, it finds the merge request
> where a teammate hit the same bug last quarter — so it's not inventing
> a fix, it's grounding its recommendation. Third, it reads the local code
> and proposes a patch plan. This Google ADK profile is deliberately
> read-only, so it cannot edit the checkout or mutate GitLab."

### 2:05 – 2:30 · Three awareness layers, fast montage (25 s)

**On screen:** Three quick cuts, ~7 s each, captioned:
1. Dynatrace trace: `agent.turn → tool.invocation` spans, args showing
   `<redacted:N chars>` (caption: "Dynatrace · every tool call traced,
   strings redacted")
2. Atlas `summaries` collection + a new session booting warm with prior
   context injected (caption: "MongoDB Atlas · remembers across sessions")
3. `search_knowledge` returning a 6-month-old issue at score 0.84
   (caption: "Elastic · hybrid search over org knowledge")

**Voiceover:**
> "And the same agent has three opt-in awareness layers: Dynatrace traces
> every tool call — with every string redacted. MongoDB Atlas gives it
> memory across sessions. Elastic lets it search your org's issues and
> CI failures semantically. All opt-in. All off by default."

### 2:30 – 2:45 · The close (15 s)

**On screen:** SECURITY.md "What leaves your machine" table for 2 s,
then the README three-layer table, then GitHub URL + live demo URL.

**Voiceover:**
> "Gemini for the brain, GitLab MCP for the superpowers, your laptop for
> the code. Open source, MIT licensed — github.com slash sechan9999
> slash LLMai. Thanks for watching."

---

## Production notes

### Tools / setup needed
- **Recorder:** OBS Studio, 1080p, 30 fps, 60% screen / 40% terminal
- **Voiceover:** record after editing, 16-bit/48 kHz; aim for ~140
  words/min
- **Cuts:** every shot ≤ 8 s; lean on jump cuts and on-screen captions

### Pre-recorded assets / seeding — STATUS as of 2026-06-10

- [x] **GitLab demo project seeded** — gitlab.com/llmai1/LLMai: Issue
      **#1** ("Login test fails on token refresh") + MR **!18**
      (postmortem hinting the inverted comparison). Re-seed anytime:
      `python scripts/seed_gitlab_demo.py` (GITLAB_PROJECT=llmai1/LLMai)
- [x] **GitLab MCP connected** — community `@zereight/mcp-gitlab` over
      stdio, read-only mode, 58 tools discovered; 16 read-only tools
      allowlisted in config.json. (Official gitlab.com MCP endpoint
      requires Premium/Ultimate + Duo — 404 on free tier.)
- [x] **Local bug planted** — `workspace/demo-login/`: both tests fail;
      the fix is one character in `auth.py` (`<` → `>=` in `needs_refresh`)
- [x] **Gemini verified** — key valid, native loop auto-resolves to
      gemini-2.5-flash
- [x] **End-to-end smoke test** — `mcp__gitlab__get_issue` fetched Issue
      #1 through the agent dispatcher in ~300 ms
- [ ] Google credentials configured; confirm ADK shows `google_agent` and
      the selected Gemini 3 model before recording
- [ ] Atlas sessions + Dynatrace/Elastic warm (only for the 25 s montage —
      cut the montage if backends aren't ready)
- [ ] One timed dry run with the exact demo prompt, then record

### What to cut if you go over 3:00
- Drop one of the three montage cuts (saves ~8 s)
- Trim Scene 2 to the config.json highlight only (saves ~8 s)

### What NOT to do
- Don't say "powered by AI" anywhere
- Don't show loading spinners — cut to result
- Don't show the permission accept-flow more than once
- Don't show real tokens/URIs on screen (use the `.env.demo` machine
  profile; double-check the terminal scrollback before recording)

---

## Voiceover script (clean copy for the narrator)

> Every AI coding agent forgets what it did yesterday and ignores what
> your team already learned. LLMai does neither — and your source code
> never leaves your laptop.
>
> LLMai is a local-first coding agent — agentic loop, eight core tools,
> explicit permission gates. Today it's running on Gemini. And this is
> the key line: a real MCP client, connected to GitLab's official MCP
> server. One config flip, zero code.
>
> On startup, LLMai spawns GitLab's MCP server as a local subprocess,
> runs the MCP handshake, and discovers its tools — namespaced
> mcp-gitlab, every one of them behind the permission system, and the
> subprocess gets a minimal environment. No inherited secrets.
>
> One prompt, one mission. Watch the plan unfold: first, the agent pulls
> the issue from GitLab over MCP. Second, it finds the merge request
> where a teammate hit the same bug last quarter — so it's not inventing
> a fix, it's reusing one. Third, it reads the local code. Fourth — and
> this matters — writing a file stops and asks me. I approve. Fifth, it
> runs the tests itself. Green. Five tool calls across two systems, and
> the only network traffic was the GitLab API calls I authorized. My
> code stayed on this machine.
>
> And the same agent has three opt-in awareness layers: Dynatrace traces
> every tool call — with every string redacted. MongoDB Atlas gives it
> memory across sessions. Elastic lets it search your org's issues and
> CI failures semantically. All opt-in. All off by default.
>
> Gemini for the brain, GitLab MCP for the superpowers, your laptop for
> the code. Open source, MIT licensed — github.com slash sechan9999
> slash LLMai. Thanks for watching.

Word count: ~330. At 140 wpm ≈ 2 min 21 s of speech — leaves ~25 s for
the visuals to breathe.

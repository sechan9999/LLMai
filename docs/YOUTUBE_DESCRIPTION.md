# LLMai — YouTube description (hackathon submission)

Ready-to-paste copy for the video upload. First two lines are what's
visible above the "...more" fold — write for them.

---

## Copy-paste block (5000-char YouTube limit, this is ~1800)

```
LLMai is a 100% local AI coding agent with three layers of awareness:
operational (Dynatrace), personal (MongoDB Atlas), organizational (Elastic).

Most coding agents forget yesterday and ignore what your team already
learned. LLMai does neither — and runs entirely on your laptop via Ollama.

This 3-minute demo shows the agent watching itself, remembering across
sessions, and searching org knowledge before writing code. Three
hackathon partner integrations, one local-first agent. Submitted to the
Google Cloud + Partners AI Agent Hackathon.

▸ Repo:    https://github.com/sechan9999/LLMai
▸ Live:    https://ll-mai.vercel.app
▸ License: MIT

────────────── Chapters ──────────────
0:00  The hook — what every other agent forgets
0:15  What LLMai is, fast
0:35  Layer 1 · Operational awareness with Dynatrace
        OpenTelemetry spans for every tool call. Bindplane routes OTLP
        to Dynatrace. agent.turn → agent.iteration → llm.chat +
        tool.invocation, with permission outcome and latency.
1:10  Layer 2 · Personal awareness with MongoDB Atlas
        Sessions, summaries, and extracted facts vector-embedded with
        Ollama nomic-embed-text. New sessions boot warm with the top-3
        recent summaries auto-injected. recall_memory tool for
        semantic recall mid-conversation.
1:50  Layer 3 · Organizational awareness with Elastic
        Hybrid keyword + dense-vector search over GitLab issues and
        docs (RRF on Atlas/Cloud, kNN fallback on basic license).
        ES|QL over pipeline-failure logs. Bindplane tees the agent's
        own OTel logs to Elastic so it can query its own behavior.
2:30  Why it matters — three layers, three partners, one agent

────────────── Quick start ──────────────
git clone https://github.com/sechan9999/LLMai
cd LLMai
make install-all
make demo-up           # ES + Kibana + Bindplane
make demo-bootstrap    # pulls embed model + creates indices
llmai-server           # → http://localhost:7777

────────────── Tech stack ──────────────
• Local LLM:       Ollama (qwen2.5-coder, nomic-embed-text)
• Agent loop:      Python · FastAPI · WebSocket streaming
• Observability:   OpenTelemetry → Bindplane → Dynatrace
• Memory:          MongoDB Atlas Vector Search (768-d cosine)
• Knowledge:       Elasticsearch (RRF hybrid + kNN fallback + ES|QL)
• MCP-compatible:  recall_memory, search_knowledge, query_logs tools
                   mirror the official MongoDB Atlas & Elastic MCP
                   server contracts
• Cloud fallback:  Groq via Vercel serverless (Web demo only)

────────────── Partner integrations ──────────────
Each is opt-in. Core agent runs 100% locally with no external dep.

▸ Dynatrace          docs/dynatrace-setup.md
▸ MongoDB Atlas      docs/atlas-setup.md
▸ Elastic            docs/elastic-setup.md

────────────── Privacy ──────────────
• Default: nothing leaves your machine.
• Each cloud layer is gated by an env var (LLMAI_OTEL_ENABLED,
  LLMAI_MEMORY_ENABLED, LLMAI_ELASTIC_ENABLED) — all default false.
• OTel span attributes carry metadata only — no file contents,
  no raw prompts.
• Memory store never exfiltrates verbatim code; extracted facts
  are short principles, not snippets.

────────────── Why these partners ──────────────
Dynatrace · MongoDB Atlas · Elastic each solve a different awareness
problem. Stacked, they turn a generic coding agent into one that
observes itself, remembers your project history, and surfaces the
issue your team filed six months ago — before writing the fix.

────────────── Credits ──────────────
Built solo for the Google Cloud + Partners AI Agent Hackathon.
Acknowledgments: Ollama (local LLM runtime), FastAPI, Rich,
OpenTelemetry, Bindplane, and the three partner backends above.

#AIAgent #LocalAI #Ollama #OpenTelemetry #MongoDBAtlas #Elastic
#Dynatrace #GoogleCloudHackathon #OpenSource #LLMai
```

---

## Notes for the upload form

- **Title (under 70 chars):** `LLMai — A local AI coding agent with three layers of awareness`
- **Tags (comma list):** `LLMai, AI coding agent, local LLM, Ollama, MongoDB Atlas, Elastic, Dynatrace, OpenTelemetry, MCP, hackathon, open source, FastAPI, vector search, ES|QL, Bindplane`
- **Category:** Science & Technology
- **Thumbnail text suggestion:** *"3 layers · 1 agent · 0 API keys"* — center-aligned, mono font, dark background matching the landing page palette (`#07090c` bg, `#46d39a` green accent)
- **Pinned comment idea:** *"Bug report and feature ideas welcome — open an issue at github.com/sechan9999/LLMai. The agent will probably triage it itself."*

## Variant: 60-second-cut description (if you upload a shorts version)

Same hook + chapters compressed:

```
LLMai — a 100% local AI coding agent with three layers of awareness:
Dynatrace (operational) · MongoDB Atlas (personal) · Elastic (organizational).

Three partners, one agent, no API keys required. Built for the Google
Cloud + Partners AI Agent Hackathon.

▸ github.com/sechan9999/LLMai
▸ ll-mai.vercel.app

#AIAgent #LocalAI #Ollama #MongoDBAtlas #Elastic #Dynatrace #Hackathon
```

## Editorial tips that matter on YouTube

1. **First 125 characters are the SEO target.** The "100% local AI coding agent with three layers of awareness" string puts the keywords up front.
2. **Chapters need 3+ entries and the first must be `0:00`** for the YouTube progress bar to render them. The block above has 6 chapters starting at 0:00 — checks the box.
3. **No more than 15 hashtags** — YouTube ignores the rest. The block has 10.
4. **Links survive a paste** if you keep them on their own line with a leading character (▸). YouTube auto-links them.
5. **Don't lead with "Hi everyone" or "In this video"** — judges scan dozens of submissions; the unique pitch goes first.

## What to swap before publishing

- Confirm the hackathon's exact name ("Google Cloud + Partners AI Agent Hackathon" is a placeholder — use the official title from the submission portal)
- Verify the live demo URL is up at upload time (`curl https://ll-mai.vercel.app`)
- Replace timestamps if the final video cut shifts shot lengths from `docs/DEMO_SCRIPT.md`

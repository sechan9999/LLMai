# Gemini and Google Cloud Agent Builder

LLMai has two distinct runtimes:

1. The default CLI/Web runtime uses LLMai's own permission-gated loop and runs on Ollama unless a cloud provider is configured.
2. The optional `google_agent` runtime uses Google's Agent Development Kit (ADK), a component of Google Cloud's agent-building stack. Gemini is the orchestrating model and GitLab's official hosted MCP server supplies GitLab tools.

The ADK profile is intentionally read-only. It can inspect workspace files, search code, and query GitLab, but it does not expose file writes, shell execution, or GitLab mutation tools. Interactive write approval remains implemented only in LLMai's CLI/Web runtime.

## Install

```bash
pip install -e ".[google-cloud]"
```

The GitLab connection also requires Node.js because ADK launches the official hosted MCP endpoint through `mcp-remote`:

```text
npx -y mcp-remote https://gitlab.com/api/v4/mcp
```

## Run with Gemini API credentials

```bash
export GOOGLE_API_KEY=YOUR_KEY
export LLMAI_GOOGLE_MODEL=gemini-3.1-pro-preview
adk web .
```

Open the URL printed by ADK and select `google_agent`. The first GitLab MCP connection opens GitLab's OAuth flow. GitLab controls account and feature eligibility for its hosted MCP server.

## Run with Vertex AI credentials

Authenticate with Google Cloud, then configure the ADK SDK to use Vertex AI:

```bash
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=global
export LLMAI_GOOGLE_MODEL=gemini-3.1-pro-preview
adk web .
```

Model availability varies by project and region. Set `LLMAI_GOOGLE_MODEL` to a Gemini 3 model that is enabled for the project used in the demo.

## What this demonstrates

- Gemini 3 is selected by the executable ADK agent configuration.
- Google ADK constructs and runs the agent.
- ADK launches `mcp-remote` against GitLab's official MCP endpoint.
- Gemini can combine GitLab context with read-only inspection of the local workspace.
- The adapter enforces a read-only profile by omitting local mutation tools and filtering MCP tool names associated with state changes.

This repository does not include proof of deployment to Vertex AI Agent Engine. Do not describe LLMai as deployed on Agent Engine unless a live deployment is created and shown separately.

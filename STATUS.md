# Status

## Active milestone

M1 — Local AI (complete).

## What works

- The repository is connected to GitHub origin/main and the M0 baseline is preserved in history.
- Python 3.12 project metadata, editable installation, pytest, and Ruff are configured.
- Safe environment-backed settings cover the gateway and local Qwen endpoint.
- Ollama is installed on the Windows host and serves qwen3.5:9b at the configured local endpoint.
- Upstream Hermes Agent 0.20.6 is installed user-scoped and configured for Ollama/qwen3.5:9b.
- Upstream Hermes one-shot generation was verified with the exact response HERMES_QWEN_OK.
- The gateway starts locally with the PowerShell development script.
- HermesService validates one-turn chat requests and returns structured responses.
- HttpQwenClient speaks the local OpenAI-compatible GET /models and POST /chat/completions protocol.
- The default local model route is qwen-local with configurable endpoint and model name.
- ModelRouter applies deterministic rules for coding, debugging, brainstorming, adversarial review, very large documents, and the Qwen default.
- Specialist routes fall back to local Qwen while Codex, Grok, and Gemini providers are not yet integrated.
- Model selection, fallback, completion, and failure events are emitted with structured JSON logging context.
- POST /api/v1/chat returns successful local responses or a structured HTTP 503 when Qwen is unavailable.
- Health checks report gateway, workflows, Hermes/Qwen, PC, Blender, and SC2 readiness.
- PC, Blender, and SC2 remain non-controlling skeletons.
- Local fake-model tests cover the HTTP protocol, Hermes, routing, fallback, validation, and unavailable-backend behavior.

## Intentionally not implemented

- Hermes conversation history, persistent memory, streaming, authentication, or a web UI.
- Codex handoff and repository coding execution.
- LangGraph execution, durable persistence, checkpoints, retries, approvals, or event storage.
- Real Windows PC control, shell execution, filesystem mutation, keyboard/mouse input, or screenshots.
- Blender bpy/MCP/CLI control or rendering.
- SC2 map/mod parsing, patching, Galaxy tooling, launching, or packaging.
- Privileged helper, public/remote access, evaluator, and skill promotion.

## Known limitations

- The default Qwen adapter assumes an OpenAI-compatible local HTTP server at http://127.0.0.1:11434/v1; endpoint and model are configurable. Ollama may start on demand, so readiness can be degraded when no request has initialized the server.
- Conversation state is request-only; conversation_id is accepted for correlation but history is not stored.
- Specialist routes are observable fallbacks to Qwen until their providers are added in later milestones.
- The gateway is a minimal standard-library development server, not a production API server.
- Workflow state is process-local and empty on restart.

## Verification

The latest verification is recorded after the M1 checks run. It uses Python 3.12.0 on Windows.

- scripts/setup.ps1: passed — editable M1 environment installed.
- scripts/check.ps1: passed — Ruff formatting/linting clean and 19 tests passed in 0.71s.
- personal_ai.dev --check: passed — gateway, workflows, Hermes/Qwen, and all integration health checks returned ready/ok.
- fake local-model chat tests: passed in the automated suite.
- live Ollama model check: passed — qwen3.5:9b and qwen3:8b were listed by the local OpenAI-compatible endpoint.
- live upstream Hermes one-shot: passed — qwen3.5:9b returned HERMES_QWEN_OK.
- live gateway chat smoke test: passed — local gateway returned a generated Qwen response through POST /api/v1/chat.

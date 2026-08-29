# Architecture

## Scope

This document describes the implemented M0 foundation and M1 local-AI slice, plus the boundaries that later milestones must preserve. The full product intent remains in MasterPlan/MasterPlan.md. M1 connects a Hermes-style conversational boundary to a configurable OpenAI-compatible local Qwen endpoint. It does not yet include Codex delegation, LangGraph durability, Blender/SC2 automation, or unrestricted PC control.

## Architectural principles

- Local-first, Windows-first, and runnable without administrator privileges.
- Hermes owns conversational interaction; LangGraph will own durable multi-stage workflows.
- Qwen is the default local model; Codex, Grok, and optional Gemini remain replaceable specialist boundaries.
- Structured APIs and application scripting remain higher priority than GUI automation.
- Every future tool returns a structured result and declares its approval level.
- The repository is the persistent handoff mechanism.

## M1 topology

```text
HTTP client / future PWA
          |
          v
services/gateway
          |
          +-----------> HermesService
          |                 |
          |                 v
          |          deterministic ModelRouter
          |                 |
          |                 v
          |          HttpQwenClient
          |                 |
          |                 v
          |       local Qwen HTTP endpoint
          |
          +-----------> services/workflows (in-memory boundary)
          +-----------> integrations/{pc,blender,sc2} (safe skeletons)

shared contracts/config/logging: src/personal_ai
```

The gateway exposes health/discovery routes and a minimal POST /api/v1/chat route. General chat is sent to the local Qwen provider. Specialist task types are routed deterministically and fall back to Qwen because Codex/Grok/Gemini providers are not yet wired. PC, Blender, and SC2 invocation attempts return a structured not_implemented result and perform no host-side action.

## Repository layout

The top-level structure follows the master plan. The shared Python package lives in src/personal_ai so configuration, logging, contracts, and development entry points can be installed cleanly. Service and integration implementations remain under their plan-defined directories.

```text
apps/web/                         future mobile-friendly PWA boundary
services/gateway/                 local HTTP gateway
services/workflows/               future LangGraph boundary
services/events/                  future event-store boundary
services/privileged-helper/       future constrained privileged boundary
integrations/{pc,blender,sc2}/    safe provider skeletons
agents/                           future routing/evaluation/specialists
skills/                           future promoted procedures
memory/                           future semantic/episodic/procedural stores
policies/                         checked-in model/tool/permission defaults
src/personal_ai/                  shared M0/M1 Python foundation
tests/                            unit, integration, and future e2e locations
```

## Runtime boundaries

### Gateway

GatewayApp is the composition root. It owns settings, Hermes, the workflow boundary, and the three integration providers. ThreadingHTTPServer remains the minimal development HTTP adapter. The gateway binds to 127.0.0.1 unless remote binding is explicitly enabled by configuration.

### Hermes and local Qwen

HermesService owns one-turn conversational handling. It validates a minimal chat request, asks ModelRouter for a deterministic selection, logs selection/fallback/outcome, and calls the configured ModelClient. HttpQwenClient uses local OpenAI-compatible GET /models and POST /chat/completions endpoints without a runtime SDK dependency. Conversation history is request-only until a later memory milestone.

The default endpoint is http://127.0.0.1:11434/v1, compatible with Ollama. The default M1 model is qwen3.8:27b, which Ollama publishes with a 256K context window and therefore satisfies the installed Hermes runtime's 64K minimum. qwen3:8b and qwen3.5:9b remain installed as optional legacy models on the inspected host. The endpoint and model are configurable through PERSONAL_AI_QWEN_BASE_URL and PERSONAL_AI_QWEN_MODEL.

The upstream Hermes Agent runtime is installed user-scoped under %LOCALAPPDATA%\\hermes (currently C:\\Users\\mrdea\\AppData\\Local\\hermes) and configured independently of this repository. M1 verifies that upstream Hermes can complete a one-shot prompt through Ollama/qwen3.8:27b. HermesService remains this repository's stable gateway boundary so later sessions can replace or embed the runtime without changing the HTTP contract.

The qwen3.8 Flash-Next preview is intentionally skipped for this Windows/AMD host. Its Ollama local tag is an MLX-oriented 125B preview with approximately 113 GB of model data, while the host's supported local acceleration path is the Windows AMD/ROCm path. Revisit only if a compatible runtime and hardware budget are explicitly established.

### Workflows

WorkflowService is an in-memory health/list boundary only. It is intentionally not a fake LangGraph implementation. Durable state, checkpoints, retries, approvals, and cancellation belong to a later milestone.

### Integrations

Each provider implements the common ToolProvider contract. SkeletonIntegration makes the safety boundary explicit: capabilities are discoverable, but no PC, Blender, or SC2 operation is enabled in M1.

### Permissions

Permission levels 0–3 are declared in policies/permissions.yaml and represented in ToolResult.approval_level. M1 has no PC/Blender/SC2 mutation endpoint and no privileged helper process. The main service must remain non-administrator.

### Observability

Logs are emitted as one JSON object per line through the standard library, including model-selection context. Health payloads identify gateway, workflows, Hermes/Qwen readiness, and all integrations. A future event service can consume the same structured result and lifecycle vocabulary without requiring a gateway rewrite.

## Development contract

The authoritative setup is pyproject.toml plus scripts/setup.ps1. The authoritative checks are scripts/check.ps1, which runs Ruff format verification, Ruff linting, and pytest. The development gateway is started with scripts/dev.ps1. The default configuration is safe for a local Windows development machine; a live Qwen endpoint is required for successful chat generation.

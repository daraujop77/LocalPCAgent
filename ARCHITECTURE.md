# Architecture

## Scope

This document describes the implementation through the bounded M18 — Secure Remote Access foundation. The full product intent remains in MasterPlan/MasterPlan.md. M4 centralizes action levels, allowlists, scoped approval requests, audit events, and a fail-closed privileged-helper boundary. M5-M13 add bounded Blender/SC2 project boundaries, restart-recoverable graph-compatible workflows, and explicit memory/skill promotion. M14 adds an authenticated socket edge, replayable events, artifact access, and filtered API reads. M15-M17 add a dependency-free mobile shell that consumes only the gateway API. M18 adds a private-network allowlist and remote-startup guard; actual Tailscale enrollment and durable identity remain deployment work. Live game/editor control and unrestricted PC control remain disabled.

## Architectural principles

- Local-first, Windows-first, and runnable without administrator privileges.
- Hermes owns conversational interaction; LangGraph will own durable multi-stage workflows.
- Qwen is the default local model; Codex, Grok, and optional Gemini remain replaceable specialist boundaries.
- Structured APIs and application scripting remain higher priority than GUI automation.
- Every future tool returns a structured result and declares its approval level.
- The repository is the persistent handoff mechanism.

## M5-M18 topology

```text
HTTP client / future PWA
          |
          v
services/gateway
          |
          +-----------> PermissionService
          |                 |
          |                 +----> validated policies/permissions.yaml
          |                 +----> process-local approvals + audit events
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
          +-----------> services/workflows (durable JSON graph boundary + recovery)
          +-----------> services/codex (permission-gated CLI handoff)
          +-----------> integrations/pc (policy-gated Windows control)
          +-----------> services/privileged_helper (disabled, fail closed)
          +-----------> integrations/blender (headless CLI + fixture bridge)
          +-----------> integrations/sc2 (structured directory/ZIP bridge)
          +-----------> memory (semantic/episodic/procedural JSON stores + Hermes context)

          +-----------> artifact catalog (metadata/download boundary)
          +-----------> apps/web (static mobile PWA shell)

shared contracts/config/logging: src/personal_ai
```

The gateway is the composition root for one shared `PermissionService`. Codex, PC, Blender, SC2, and the privileged-helper boundary consult the same immutable action policy. General chat cannot silently trigger a repository or host mutation. Workflow runs use explicit nodes and persisted state; integrations return the common structured result envelope. The socket adapter applies optional bearer authentication, an explicit CORS origin allowlist, and a CSRF header for browser writes before dispatching API requests.

## Repository layout

The top-level structure follows the master plan. The shared Python package lives in src/personal_ai so configuration, logging, contracts, and development entry points can be installed cleanly. Service and integration implementations remain under their plan-defined directories.

```text
apps/web/                         future mobile-friendly PWA boundary
services/gateway/                 local HTTP gateway
services/workflows/               durable graph-compatible workflow boundary
services/events/                  future event-store boundary
services/privileged-helper/       human-readable privileged boundary documentation
services/privileged_helper/       importable M4 fail-closed service contract
integrations/pc/                   controlled Windows host provider and native backend
integrations/blender/              headless Blender bridge and fixture backend
integrations/sc2/                  structured SC2 project bridge
services/codex/                     observable Codex CLI handoff service
agents/                           future routing/evaluation/specialists
skills/                           future promoted procedures
memory/                           JSON semantic/episodic/procedural stores
policies/                         checked-in model/tool/permission defaults
src/personal_ai/                  shared Python contracts, config, logging, and model boundary
tests/                            unit, integration, and future e2e locations
```

## Runtime boundaries

### Gateway

GatewayApp is the composition root. It owns settings, one PermissionService, Hermes, the workflow service, Codex handoff, the privileged boundary, memory, and the three integration providers. ThreadingHTTPServer remains the minimal development HTTP adapter. The gateway binds to 127.0.0.1 unless remote binding is explicitly enabled by configuration.

Remote binding is intended only behind a private network such as a Tailscale tailnet. `PERSONAL_AI_ALLOW_REMOTE=true` requires `PERSONAL_AI_API_TOKEN` and a non-empty `PERSONAL_AI_ALLOWED_CLIENT_NETWORKS` list. Every socket peer, including CORS preflight requests, must fall inside one of those CIDR ranges; the default list contains only `127.0.0.1/32`. The gateway exposes only its bounded API routes and never binds Hermes, Qwen, Blender, SC2, Codex, or the privileged helper as separate public services. Set `PERSONAL_AI_ALLOW_REMOTE=false` to roll back immediately to loopback-only mode.

### Web shell

The M15–M17 web surface is a static PWA under `apps/web`. It is intentionally a client of the gateway rather than a second orchestration layer: chat, monitoring, approvals, run controls, artifacts, and health use `/api/v1` only. The shell stores its configured gateway URL and token in browser local storage; richer identity/session management remains future work after the M18 gateway-side boundary.

### Hermes and local Qwen

HermesService owns one-turn conversational handling. It validates a minimal chat request, asks ModelRouter for a deterministic selection, logs selection/fallback/outcome, adds bounded matching episodic context when memory is configured, and calls the configured ModelClient. HttpQwenClient uses local OpenAI-compatible GET /models and POST /chat/completions endpoints without a runtime SDK dependency. Full conversation history remains request-only.

The default endpoint is http://127.0.0.1:11434/v1, compatible with Ollama. The default M1 model is qwen3.8:27b, which Ollama publishes with a 256K context window and therefore satisfies the installed Hermes runtime's 64K minimum. qwen3:8b and qwen3.5:9b remain installed as optional legacy models on the inspected host. The endpoint and model are configurable through PERSONAL_AI_QWEN_BASE_URL and PERSONAL_AI_QWEN_MODEL.

The host benchmark recommends a 64K runtime profile for normal Qwen3.8 operation. A 128K profile completed successfully, but it moved part of the model off the GPU and was materially slower on warm requests. Ollama's OpenAI-compatible API does not expose context-size selection; an explicit 64K or 128K profile therefore requires an Ollama Modelfile alias or a native Ollama API path. The current repository client remains transport-compatible and does not silently claim a context size it has not configured.

The upstream Hermes Agent runtime is installed user-scoped under %LOCALAPPDATA%\\hermes (currently C:\\Users\\mrdea\\AppData\\Local\\hermes) and configured independently of this repository. M1 verifies that upstream Hermes can complete a one-shot prompt through Ollama/qwen3.8:27b. HermesService remains this repository's stable gateway boundary so later sessions can replace or embed the runtime without changing the HTTP contract.

The qwen3.8 Flash-Next preview is intentionally skipped for this Windows/AMD host. Its Ollama local tag is an MLX-oriented 125B preview with approximately 113 GB of model data, while the host's supported local acceleration path is the Windows AMD/ROCm path. Revisit only if a compatible runtime and hardware budget are explicitly established.

### Local model benchmark

The benchmark used Ollama's native chat API with a short deterministic prompt, `think=false`, and `num_predict=64`. Process memory was sampled from the Ollama processes; VRAM and loaded-model size came from Ollama's `/api/ps` endpoint. These results measure context-profile overhead and short-request speed, not full 64K/128K document comprehension.

| Profile | Warm latency | Output speed | Ollama loaded model / VRAM | Peak private process memory | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| qwen3.8:27b, 64K | 228 ms | ~49 tok/s | 16.33 GB / 16.33 GB | 21.16 GB | Recommended primary profile; full GPU residency observed |
| qwen3.8:27b, 128K | 1,195 ms | ~16 tok/s | 18.48 GB / 14.03 GB | 23.05 GB | Works, but partial CPU offload and lower speed |
| qwen3:8b, 32K | 127 ms | ~55 tok/s request latency | 9.28 GB / 9.28 GB | 9.64 GB | Recommended light-task candidate; not the Hermes 64K default |

### Codex handoff

Hermes exposes an explicit `delegate_to_codex` boundary. Gateway coding handoffs pass through that Hermes boundary and then to CodexHandoffService, which validates that a requested path is an existing Git root, optionally checks the caller's starting revision, and asks PermissionService to authorize the exact repository/task/test scope. Only an accepted, unexpired, unused level-2 approval starts `codex exec`. The service captures a content baseline immediately before execution, reports the before-existing files separately, observes the after-state delta, runs supplied argv tests without a shell, and never commits or pushes.

### PC control

PcIntegration is an execution boundary over NativeWindowsPcControl and no longer owns hardcoded approval levels. PermissionService authorizes every action first. Application names resolve once to trusted executable paths and caller-supplied paths are rejected. PowerShell uses a structured verb/argv contract, quotes values safely, rejects expansion/injection syntax, and resolves path arguments beneath the workspace. File operations remain bounded by PERSONAL_AI_PC_WORKSPACE_ROOT. Level-2 operations require an exact one-time approval ID. Legacy `approval_granted` parameters are stripped from the scope and never authorize execution. Subprocess timeouts return structured failures; the provider does not elevate or expose arbitrary shell/process control.

The `scripts/pc-acceptance.ps1` script is intentionally opt-in. It launches an allowlisted Notepad instance, focuses it through the window contract, types known text, saves a working file, reads it back, and closes the window. Automated tests use a fake backend for host operations and never open GUI applications.

### Blender bridge

`BlenderIntegration` uses the central permission service and a replaceable backend. `LocalBlenderBackend` supports JSON scene fixtures for deterministic tests and invokes a configured Blender executable in background mode for `.blend` inspection, controlled `bpy` operations, working-copy changes, and preview/final rendering. Callers provide structured operations; free-form Python is not accepted. Mutation targets are required to resolve below the managed artifact root; source files outside that root are rejected even when the caller has an approval.

### SC2 bridge

`Sc2Integration` uses the central permission service and `LocalSc2Backend`. It inspects bounded project directories and ZIP-compatible `.SC2Map`/`.SC2Mod` files, searches text/XML, returns an entity/field index for structured dependencies, creates snapshots, patches text only in the managed working-copy root, validates Galaxy syntax heuristically, and packages versions. Galaxy Editor and game launch are explicit disabled results until an audited executable/tool contract is added.

### Workflows

`WorkflowService` is a durable graph-compatible runner. Each named node receives JSON-compatible state, emits lifecycle events, and checkpoints atomically after completion under `artifacts/workflows/`. Runs interrupted during service downtime are marked and can be automatically recovered after definitions are registered; runs can also pause, resume, retry, cancel, and accept steering instructions. The engine is intentionally independent of the LangGraph import; the optional adapter is a compatibility probe, not the default executor yet.

### Memory and learning

`MemoryService` composes a semantic last-write-wins JSON store, append-only episodic JSONL records, and versioned procedural skills. Hermes receives bounded search context from matching episodes. Repeated successful workflow procedures can create an unpromoted candidate with episode provenance; a candidate must pass repeated explicit validation and is promoted only by an explicit call. A failed candidate never overwrites a promoted version.

### Integrations

Each provider implements the common ToolProvider contract. PC remains the controlled Windows host provider. Blender and SC2 are structured project providers; their mutation actions are centrally approval-gated and their GUI/game fallbacks remain disabled.

### Permissions and privileged boundary

`PermissionPolicy` loads the checked-in JSON-compatible `policies/permissions.yaml` and validates exact levels 0–3, action assignments, PC allowlists, non-admin main-process configuration, and privileged-helper allowlists. Levels 0/1 are automatic; levels 2/3 require approval. Requests are scoped by a canonical SHA-256 digest of action, target, and sanitized parameters, expire after the policy TTL, and are consumed once. Rejected, cancelled, expired, mismatched, reused, and unknown approvals all fail closed.

The M4 approval/event store is thread-safe but process-local. It is intentionally not a durable authorization system. The API exposes request and decision lifecycle for local development. Remote binding additionally requires a bearer token and an explicit private client-network allowlist, and browser origins/writes are constrained by the M14 socket policy; durable identity and approval storage remain future work.

`PrivilegedHelperService` defines the future transport/backend contract. Its M4 backend is disabled. Policy authorization occurs before a future helper call, privileged actions must be level 3 and helper-allowlisted, and accepted approval alone is insufficient. With helper policy disabled, the request returns `privileged_helper_unavailable` without consuming the approval or invoking any transport. The main gateway never requests administrator privileges.

### Observability

Logs are emitted as one JSON object per line through the standard library. Permission requests/decisions/consumption also create process-local structured audit events. Workflow events are persisted as JSONL and can be replayed as run-scoped SSE with an event cursor. Run state exposes task, current step, tools, artifacts, changed files, warnings, errors, approval state, and iteration. Artifact metadata includes content type, size, and run provenance while downloads are limited to the artifact root. Health identifies permissions, memory, workflows, Hermes/Qwen, Codex, PC, Blender, SC2, and the disabled privileged boundary.

## Development contract

The authoritative setup is pyproject.toml plus scripts/setup.ps1. The authoritative checks are scripts/check.ps1. The development gateway starts with scripts/dev.ps1. The optional PC acceptance exercises the M4 approval API. Blender live work additionally requires a configured Blender executable; SC2 project operations use standard-library parsers and do not require the game/editor. A live Qwen endpoint is required for chat generation, and the Codex CLI is required only for real handoffs.

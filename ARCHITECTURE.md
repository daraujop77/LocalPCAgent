# Architecture

## Scope

This document describes the implemented M0 foundation and the boundaries that later milestones must preserve. The full product intent remains in [`MasterPlan/MasterPlan.md`](MasterPlan/MasterPlan.md). M0 does not connect a conversational agent, local model, LangGraph, Blender, SC2, or unrestricted PC control.

## Architectural principles

- Local-first, Windows-first, and runnable without administrator privileges.
- Hermes will own conversational interaction; LangGraph will own durable multi-stage workflows.
- Qwen is the default local model; Codex, Grok, and optional Gemini remain replaceable specialist boundaries.
- Structured APIs and application scripting remain higher priority than GUI automation.
- Every future tool returns a structured result and declares its approval level.
- The repository is the persistent handoff mechanism. The handoff files at the root are part of the system design, not optional notes.

## M0 topology

```text
HTTP client / future PWA
          |
          v
services/gateway  ----> services/workflows (in-memory boundary)
          |
          +-----------> integrations/pc      (safe skeleton)
          +-----------> integrations/blender (safe skeleton)
          +-----------> integrations/sc2     (safe skeleton)

shared contracts/config/logging: src/personal_ai
```

The gateway currently exposes read-only health and discovery routes. The integration classes advertise future capability names, but all invocation attempts return a structured `not_implemented` result and perform no host-side action. This is deliberate: M0 defines interfaces without starting M3, M5, or M8 implementation.

## Repository layout

The top-level structure follows the master plan. The shared Python package lives in `src/personal_ai` so configuration, logging, contracts, and development entry points can be installed cleanly. Service and integration implementations remain under their plan-defined directories so future agents can locate ownership without conversation history.

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
src/personal_ai/                  shared M0 Python foundation
tests/                            unit, integration, and future e2e locations
```

## Runtime boundaries

### Gateway

`GatewayApp` is the composition root. It owns settings, the workflow boundary, and the three integration providers. `ThreadingHTTPServer` is used for M0 to avoid adding a runtime web dependency before the API surface stabilizes. The gateway binds to `127.0.0.1` unless remote binding is explicitly enabled by configuration.

### Workflows

`WorkflowService` is an in-memory health/list boundary only. It is intentionally not a fake LangGraph implementation. Durable state, checkpoints, retries, approvals, and cancellation belong to a later milestone.

### Integrations

Each provider implements the common `ToolProvider` contract. The shared `SkeletonIntegration` makes the safety boundary explicit: capabilities are discoverable, but no PC, Blender, or SC2 operation is enabled in M0.

### Permissions

Permission levels 0–3 are declared in `policies/permissions.yaml` and represented in `ToolResult.approval_level`. M0 has no mutation endpoint and no privileged helper process. The main service must remain non-administrator.

### Observability

Logs are emitted as one JSON object per line through the standard library. Health payloads identify gateway, workflows, and all integrations. A future event service can consume the same structured result and lifecycle vocabulary without requiring a gateway rewrite.

## Development contract

The authoritative setup is `pyproject.toml` plus `scripts/setup.ps1`. The authoritative checks are `scripts/check.ps1`, which runs Ruff format verification, Ruff linting, and pytest. The default configuration is safe for a local Windows development machine.


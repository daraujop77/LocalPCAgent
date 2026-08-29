# Architecture decisions

## ADR-001 — Use the plan-defined monorepo at the repository root

Decision: Keep `apps`, `services`, `integrations`, `agents`, `skills`, `memory`, `policies`, `artifacts`, `logs`, `tests`, and `docs` at the root, with the shared installable Python package under `src/personal_ai`.

Reason: This preserves the master plan's ownership boundaries while giving shared Python code a conventional package layout for editable installs and future service extraction.

Date: 2026-08-29

## ADR-002 — Keep M0 runtime dependencies in the standard library

Decision: Use `http.server`, dataclasses, environment configuration, and standard-library logging for the M0 runtime. Declare pytest and Ruff as development dependencies.

Reason: The inspected Windows host has Python 3.12 but no Node.js, and the M0 acceptance criteria require foundation and health checks rather than a production web framework. This keeps the first environment reproducible and leaves framework selection open for M1+.

Date: 2026-08-29

## ADR-003 — Expose integration contracts before enabling control

Decision: PC, Blender, and SC2 providers expose health, capability discovery, and structured `not_implemented` results only. No host-control or mutation endpoint exists in M0.

Reason: The master plan requires explicit interfaces, structured tools, and GUI automation as a fallback. Defining the boundary now prevents accidental unrestricted control while preserving the later structured API/bpy/SC2 tooling direction.

Date: 2026-08-29

## ADR-004 — Bind locally by default

Decision: The gateway binds to loopback unless `PERSONAL_AI_ALLOW_REMOTE=true` is explicitly configured. Even when enabled, the configured host is used only by the development server; no public exposure or private-network setup is included in M0.

Reason: The platform is local-first and the master plan explicitly forbids exposing raw agent services publicly. Safe defaults matter before the permission and remote-access milestones exist.

Date: 2026-08-29

## ADR-005 — Keep handoff documents as operational state

Decision: `ARCHITECTURE.md`, `STATUS.md`, `NEXT.md`, `DECISIONS.md`, `TOOL_CONTRACTS.md`, and `ROADMAP.md` are maintained in the repository at every milestone boundary.

Reason: Future Codex, Hermes, and local-Qwen sessions must continue without relying on previous conversation context.

Date: 2026-08-29


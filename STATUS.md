# Status

## Active milestone

M14 — Web Gateway foundation is complete. M5–M13 now reflect their verified bounded scope; M15 — Web Chat / PWA shell is next.

## What works

- The gateway loads and validates `policies/permissions.yaml` at startup. It rejects missing, malformed, incomplete, or unsafe policy configuration.
- Levels 0 and 1 execute automatically. Levels 2 and 3 create approval requests and do not invoke their backend before authorization.
- Approvals have generated IDs and requested, accepted, rejected, cancelled, and expired states. They expire after the configured TTL, bind to the exact action/target/sanitized parameters, and are consumed once.
- Approval requests and lifecycle events are visible through `/api/v1/approvals`, `/api/v1/approvals/{id}`, and `/api/v1/approvals/events`. They are process-local in M4.
- Codex repository handoffs and PC actions use the shared `PermissionService`. `approval_granted: true` is ignored and cannot bypass policy.
- PC application and PowerShell verb allowlists are owned by the validated permission policy. Workspace path restrictions and native Windows controls from M3 remain active.
- M3 remediation now launches only startup-resolved allowlisted executable paths, uses structured PowerShell arguments with workspace path resolution, and converts subprocess timeouts into structured failures.
- Hermes now owns the explicit delegation boundary to Codex. Codex handoffs report pre-existing files separately from the content delta produced during the handoff.
- Qwen readiness verifies that the configured model ID is present in the local `/models` response.
- `/api/v1/permissions` exposes the active policy summary. Health and tool discovery report the permission service and privileged-helper boundary.
- A level-3 privileged action requires normal scoped approval and still fails closed because no elevated helper executable or transport is enabled. The gateway/main service remains non-administrator.
- The local gateway, Hermes/Qwen boundary, observable Codex handoff, and controlled PC provider from earlier milestones remain available.
- Blender provides a permission-gated headless bridge with JSON scene fixtures, `.blend` background inspection, controlled structured `bpy` operations, artifact-root working-copy enforcement, material creation, and preview/final render contracts. Original source targets are rejected for mutation.
- SC2 provides permission-gated directory/ZIP project inspection, search, XML/structured reads, an entity/field index, safe snapshots, artifact-root working-copy text patches, heuristic Galaxy checks, log collection, and packaging. Editor/game launch remains disabled.
- WorkflowService persists atomic JSON run checkpoints and JSONL lifecycle events after every node, supports retry, interruption recovery, pause/resume/cancel, steering, filtered event reads, and run-scoped SSE replay.
- MemoryService persists semantic facts, append-only episodic execution records, Hermes history context, and versioned procedural skill candidates. Repeated successful workflow procedures can suggest an unpromoted candidate; explicit validation and promotion remain required.
- `/api/v1/blender/invoke`, `/api/v1/sc2/invoke`, `/api/v1/workflows`, `/api/v1/runs`, run controls, filtered memory endpoints, `/api/v1/artifacts`, artifact downloads, and SSE event replay are available through the local gateway.
- The HTTP edge supports optional bearer authentication, CORS origin allowlisting, CSRF protection for browser writes, and refuses remote startup without an API token.

## Intentionally not implemented

- No privileged helper process, installation, named-pipe server, elevated operation, or helper allowlist is enabled.
- Approval and permission audit records remain process-local; they do not yet have durable storage or multi-user identity.
- Live Blender validation on this host if no Blender executable is configured; JSON fixture coverage is deterministic.
- Natural-language Blender planning, visual evaluation/revision, MPQ-native SC2 parsing, Galaxy Editor/game launch, LangGraph as the default executor, web PWA, durable approvals, private-network deployment, and a production database.
- Unrestricted shell, arbitrary application launch, arbitrary process termination, or unrestricted GUI automation.

## Known limitations

- Restarting the gateway clears approval requests, audit events, and Codex run records; interrupted workflow runs are recovered after definitions are registered, while workflow state/events and memory records remain local files.
- The local default has no token for convenience; set `PERSONAL_AI_API_TOKEN` and `PERSONAL_AI_ALLOWED_ORIGINS` before any remote or browser deployment.
- `policies/permissions.yaml` is JSON-compatible YAML so the runtime can validate it with the Python standard library. General YAML syntax is not accepted.
- Codex execution still requires a locally installed/authenticated Codex CLI. Automated tests use a fake backend.
- The opt-in Notepad acceptance changes desktop state and was not run automatically in this cycle.
- LangGraph is optional and not the default executor yet; the repository-owned runner keeps the persisted state/event contract stable for a future migration.

## Verification

Verification was run on Windows with the repository Python 3.12 environment.

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m pytest -q`: passed — 67 tests.
- `scripts/check.ps1`: passed — Ruff formatting/linting and 67 tests.
- Optional LangGraph extra remains installed and the adapter smoke-test passes; the gateway still uses the repository-owned persisted checkpoint runner.
- Permission acceptance coverage proves automatic safe actions, paused destructive actions, lifecycle transitions, expiry, exact scope binding, one-time consumption, legacy-boolean non-bypass, and privileged fail-closed behavior.
- Gateway integration coverage proves approval acceptance and audited execution for PC/Codex plus the disabled privileged boundary.
- Live `scripts/pc-acceptance.ps1`: updated to use M4 approval IDs; not run because it intentionally controls Notepad.

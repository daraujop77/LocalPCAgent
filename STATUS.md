# Status

## Active milestone

M4 — Permission System is complete. M5 — Blender Bridge has not started.

## What works

- The gateway loads and validates `policies/permissions.yaml` at startup. It rejects missing, malformed, incomplete, or unsafe policy configuration.
- Levels 0 and 1 execute automatically. Levels 2 and 3 create approval requests and do not invoke their backend before authorization.
- Approvals have generated IDs and requested, accepted, rejected, cancelled, and expired states. They expire after the configured TTL, bind to the exact action/target/sanitized parameters, and are consumed once.
- Approval requests and lifecycle events are visible through `/api/v1/approvals`, `/api/v1/approvals/{id}`, and `/api/v1/approvals/events`. They are process-local in M4.
- Codex repository handoffs and PC actions use the shared `PermissionService`. `approval_granted: true` is ignored and cannot bypass policy.
- PC application and PowerShell verb allowlists are owned by the validated permission policy. Workspace path restrictions and native Windows controls from M3 remain active.
- `/api/v1/permissions` exposes the active policy summary. Health and tool discovery report the permission service and privileged-helper boundary.
- A level-3 privileged action requires normal scoped approval and still fails closed because no elevated helper executable or transport is enabled. The gateway/main service remains non-administrator.
- The local gateway, Hermes/Qwen boundary, observable Codex handoff, and controlled PC provider from earlier milestones remain available.
- Blender and SC2 remain safe, non-controlling skeletons.

## Intentionally not implemented

- No privileged helper process, installation, named-pipe server, elevated operation, or helper allowlist is enabled.
- Approval and event records are not durable and have no authentication or multi-user identity model.
- M5 Blender inspection, controlled `bpy`, working copies, rendering, and artifact creation.
- LangGraph durable workflows, memory, web PWA, remote access, and SC2 automation.
- Unrestricted shell, arbitrary application launch, arbitrary process termination, or unrestricted GUI automation.

## Known limitations

- Restarting the gateway clears approval requests, audit events, Codex run records, and workflow records.
- Approval decisions are exposed by a local development API without authentication; keep the gateway loopback-only.
- `policies/permissions.yaml` is JSON-compatible YAML so the runtime can validate it with the Python standard library. General YAML syntax is not accepted.
- Codex execution still requires a locally installed/authenticated Codex CLI. Automated tests use a fake backend.
- The opt-in Notepad acceptance changes desktop state and was not run automatically in this cycle.

## Verification

Verification was run on Windows with the repository Python 3.12 environment.

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m pytest -q`: passed — 41 tests.
- Permission acceptance coverage proves automatic safe actions, paused destructive actions, lifecycle transitions, expiry, exact scope binding, one-time consumption, legacy-boolean non-bypass, and privileged fail-closed behavior.
- Gateway integration coverage proves approval acceptance and audited execution for PC/Codex plus the disabled privileged boundary.
- Live `scripts/pc-acceptance.ps1`: updated to use M4 approval IDs; not run because it intentionally controls Notepad.

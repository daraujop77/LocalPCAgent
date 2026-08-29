# Tool contracts

This file is the stable M5-M13 contract for gateway clients and future agents. All mutation-capable providers must use the central permission service before invoking a backend.

## Common tool result

~~~json
{
  "success": false,
  "tool": "pc.input.type",
  "action": "pc.input.type",
  "target": null,
  "summary": "pc.input.type was not authorized by the central permission policy.",
  "changed_files": [],
  "artifacts": [],
  "data": {"permission": {}},
  "logs": [],
  "warnings": ["No host operation was invoked."],
  "error": "approval_required",
  "reversible": true,
  "approval_level": 2,
  "duration_ms": null
}
~~~

Stable fields are `success`, `tool`, `action`, `target`, `summary`, `changed_files`, `artifacts`, `data`, `logs`, `warnings`, `error`, `reversible`, `approval_level`, and `duration_ms`.

## Permission levels

| Level | Policy meaning | Execution |
| ---: | --- | --- |
| 0 | Read-only | Automatic |
| 1 | Safe and reversible | Automatic |
| 2 | Potentially destructive | Exact approval required |
| 3 | Sensitive or privileged | Exact approval plus enabled/allowlisted helper required |

`policies/permissions.yaml` is authoritative for action levels and PC allowlists. Gateway startup validates the policy. Providers must not maintain a second level map or trust caller-provided levels.

## Approval lifecycle

A level-2/3 invocation without `approval_id` returns `approval_required` and creates:

~~~json
{
  "approval_id": "generated-id",
  "action": "pc.input.type",
  "target": null,
  "level": 2,
  "status": "requested",
  "scope_digest": "sha256",
  "reason": "Action requires explicit approval.",
  "requested_by": "gateway",
  "requested_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "decided_at": null,
  "decided_by": null,
  "decision_reason": null,
  "consumed_at": null
}
~~~

Valid terminal decisions are `accepted`, `rejected`, and `cancelled`; an undecided or accepted request can become `expired` at TTL. Only `accepted` can authorize. Authorization requires the same action, target, and sanitized parameters used to create the request. `approval_id` and legacy `approval_granted` are excluded from the scope. An approval is consumed once before backend execution and cannot be replayed.

Stable denial errors include `approval_required`, `approval_not_found`, `approval_rejected`, `approval_cancelled`, `approval_expired`, `approval_scope_mismatch`, `approval_already_used`, `unsupported_action`, `privileged_helper_unavailable`, and `privileged_action_not_allowlisted`.

## HTTP routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health`, `/health/ready`, `/api/v1/health` | Readiness |
| GET | `/health/live` | Process liveness |
| GET | `/api/v1/tools` | Capability discovery |
| POST | `/api/v1/chat` | One-turn Hermes/local-Qwen chat |
| GET/POST | `/api/v1/codex/health`, `/api/v1/codex/handoff` | Codex readiness/handoff |
| GET | `/api/v1/codex/runs` | Process-local handoff records |
| GET/POST | `/api/v1/pc/health`, `/api/v1/pc/invoke` | PC readiness/invocation |
| GET/POST | `/api/v1/blender/invoke` | Headless Blender/fixture operations |
| GET/POST | `/api/v1/sc2/invoke` | Structured SC2 project operations |
| GET/POST | `/api/v1/workflows` | List definitions or start a durable workflow run |
| GET | `/api/v1/runs` | Durable workflow runs |
| GET/POST | `/api/v1/runs/{id}` and controls | Inspect, pause, resume, retry, cancel, or steer a run |
| GET | `/api/v1/memory/episodes`, `/api/v1/memory/semantic`, `/api/v1/memory/skills` | Read local memory records |
| GET | `/api/v1/permissions` | Active validated policy summary |
| GET/POST | `/api/v1/approvals` | List or explicitly create requests |
| GET | `/api/v1/approvals/{id}` | Read and refresh one request |
| POST | `/api/v1/approvals/{id}/accept` | Accept requested approval |
| POST | `/api/v1/approvals/{id}/reject` | Reject requested approval |
| POST | `/api/v1/approvals/{id}/cancel` | Cancel requested approval |
| GET | `/api/v1/approvals/events` | Process-local lifecycle audit |
| GET/POST | `/api/v1/privileged/health`, `/api/v1/privileged/invoke` | Disabled privileged boundary |

Unknown routes return 404 and unsupported methods return 405. A pending approval returns 409. Rejected/expired/mismatched/reused/privileged denials return 403. Input validation returns 400. Other provider validation failures return 422.

An explicit approval request body is:

~~~json
{
  "action": "pc.input.type",
  "target": null,
  "parameters": {"text": "exact text"},
  "reason": "Why this action is wanted",
  "requested_by": "local-user"
}
~~~

A decision body optionally contains `decided_by` and `reason`. There is no authentication or durable identity in M5-M13; keep the API on loopback.

## Codex repository handoff

~~~json
{
  "task_id": "optional-correlation-id",
  "repository_path": "D:/work/repository",
  "task": "Implement the requested change",
  "starting_revision": "optional-git-revision",
  "constraints": ["Do not commit changes"],
  "test_command": ["python", "-m", "pytest", "-q"],
  "test_timeout_seconds": 120,
  "approval_id": "accepted-id-on-second-call"
}
~~~

First call without `approval_id`, accept the returned request, then repeat the exact handoff with that ID. The gateway routes this explicit handoff through Hermes's `delegate_to_codex` boundary. The permission scope excludes generated `task_id` and uses the resolved Git-root target plus task, revision, constraints, test argv, and timeout. The backend runs `codex exec --ephemeral --json --sandbox workspace-write`, reports `preexisting_files` separately, reports the before/after content delta in `changed_files`, runs tests as argv without a shell, and never commits or pushes.

## Controlled PC invocation

~~~json
{
  "action": "pc.files.patch",
  "target": "working/file.txt",
  "parameters": {
    "replacements": [{"old": "before", "new": "after"}],
    "approval_id": "accepted-id"
  }
}
~~~

M3 actions remain available for system/process inspection, allowlisted applications, workspace-bounded files, restricted PowerShell, windows, screenshots, and fallback input. Application names are resolved to trusted paths before launch. PowerShell accepts `verb` plus an `args` string array, not a free-form `script`:

~~~json
{
  "action": "pc.shell.powershell",
  "parameters": {
    "verb": "Get-ChildItem",
    "args": ["-Path", "working"]
  }
}
~~~

PowerShell values are safely quoted and path arguments are resolved under `PERSONAL_AI_PC_WORKSPACE_ROOT`; expansion, injection syntax, absolute paths, and parent traversal are rejected. Subprocess timeouts return structured failures. The provider never elevates.

## Privileged helper

`privileged.system.execute` exists only to prove the boundary. It is level 3, the helper policy is disabled, its action allowlist is empty, and the backend performs no operation. Even an accepted approval returns `privileged_helper_unavailable`. A future implementation must keep central authorization, use an authenticated constrained transport, independently validate arguments, and expose only specific allowlisted operations.

## Blender invocation

~~~json
{
  "action": "blender.inspect_scene",
  "target": "working/scene.blend",
  "parameters": {}
}
~~~

Read-only scene inspection accepts `.blend` files when a Blender executable is configured and JSON scene fixtures for deterministic tests. Mutating operations require a working-copy target and level-2 approval. `blender.execute_bpy` accepts an `operations` array with allowlisted operation names (`transform`, `material_color`, `camera_configure`, `set_render_engine`); arbitrary Python source is rejected. `blender.save_copy` and render operations report relative artifact paths.

## SC2 invocation

~~~json
{
  "action": "sc2.galaxy.patch",
  "target": "artifacts/sc2/my-working-copy",
  "parameters": {
    "file": "Map.galaxy",
    "search": "oldValue",
    "replace": "newValue",
    "approval_id": "accepted-id"
  }
}
~~~

SC2 reads operate on bounded directories or ZIP-compatible `.SC2Map`/`.SC2Mod` files. Snapshot, patch, validation, and package results identify working copies and artifacts. Editor/game launch returns `sc2_runtime_unavailable` until an audited adapter is installed.

## Durable workflow and memory boundaries

`POST /api/v1/workflows` accepts `workflow`, optional `task`, JSON-compatible `state`, and `background`. Standard definitions are `blender.autonomous` and `sc2.modification`. Each run exposes `run_id`, `workflow`, `status`, `state`, `plan`, `current_step`, `artifacts`, `changed_files`, `warnings`, `errors`, `approval_required`, `approval_status`, `iteration`, `tool_history`, and timestamps. Lifecycle events are stored as JSONL under `artifacts/workflows/`. Run controls are explicit and do not grant tool approval.

Episodic records capture successful and failed runs. Semantic records are keyed facts. Procedural skill candidates retain source episode IDs and validation provenance; repeated validation plus an explicit promotion call is required before a candidate becomes the active version.

## Chat and workflow boundaries

`POST /api/v1/chat` retains the M1 request fields `message`, optional `conversation_id`, `task_type`, and `system_prompt`. It routes visibly to configured specialists and falls back to local Qwen where a specialist is unavailable. `WorkflowService` provides durable JSON checkpoints and a graph-compatible state/event boundary; a LangGraph adapter remains optional until migration tests are added.

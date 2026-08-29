# Tool contracts

M0 exposes only read-only gateway routes and provider discovery. The listed PC, Blender, and SC2 capability names are reserved contracts, not executable tools yet.

## Common result envelope

Every future tool invocation must serialize the `ToolResult` shape:

```json
{
  "success": false,
  "tool": "pc.shell.powershell",
  "action": "pc.shell.powershell",
  "target": null,
  "summary": "pc.shell.powershell is defined but not implemented in M0",
  "changed_files": [],
  "artifacts": [],
  "logs": [],
  "warnings": ["No host application or PC control was invoked."],
  "error": "not_implemented",
  "reversible": true,
  "approval_level": 0,
  "duration_ms": null
}
```

Required fields are stable across providers: `success`, `tool`, `action`, `target`, `summary`, `changed_files`, `artifacts`, `logs`, `warnings`, `error`, `reversible`, `approval_level`, and `duration_ms`.

`approval_level` uses the master-plan scale: 0 read-only, 1 safe reversible, 2 potentially destructive, and 3 sensitive/privileged. The main AI service must not bypass this field or gain administrator shell access.

## Provider interface

Each provider implements:

```python
health() -> HealthStatus
capabilities() -> tuple[str, ...]
invoke(action, *, target=None, parameters=None) -> ToolResult
```

M0 behavior:

- `health()` reports `ready: true`, `mode: skeleton`, and `control_enabled: false`.
- `capabilities()` returns the reserved names below.
- `invoke()` always returns `success: false`, `error: not_implemented`, and performs no external action.

## M0 HTTP routes

All routes are `GET` only. Unknown routes return `404`; non-GET methods return `405`.

| Route | Purpose |
| --- | --- |
| `/` | Service identity and running message |
| `/health` | Readiness summary for all M0 components |
| `/health/ready` | Same readiness summary, suitable for a readiness probe |
| `/health/live` | Process liveness response without dependency checks |
| `/api/v1/health` | Versioned readiness summary |
| `/api/v1/tools` | Provider/capability discovery; execution is marked `disabled_in_m0` |
| `/api/v1/runs` | Empty in-memory workflow run list |

Health component names are `gateway`, `workflows`, `pc`, `blender`, and `sc2`. A readiness response is `200` when all are ready and `503` otherwise.

## Reserved provider capabilities

### PC

`pc.system_info`, `pc.list_processes`, `pc.apps.launch`, `pc.files.read`, `pc.shell.powershell`, `pc.screen.capture`.

No unrestricted PC control is implemented. Future destructive actions must use working copies, allowlists, and permission levels.

### Blender

`blender.status`, `blender.inspect_scene`, `blender.save_copy`, `blender.execute_bpy`, `blender.render.preview`.

Future control should prefer bpy/MCP/headless CLI and preserve the original `.blend` through a working-copy workflow.

### SC2

`sc2.project.inspect`, `sc2.project.snapshot`, `sc2.search`, `sc2.galaxy.validate`.

Future control should prefer structured project files and Galaxy tooling. External publishing remains approval-required.

## Workflow boundary

The M0 workflow service provides `health()` and `list_runs()` only. LangGraph state, checkpoints, human approval, pause/resume/cancel, retries, artifacts, and events are future contracts and must not be implied by the current empty run list.


# Tool contracts

M2 and M3 expose observable Codex delegation and controlled Windows PC operations. Blender and SC2 capability names remain discovery contracts and are not executable.

## Common result envelope

Future tool invocations must serialize the ToolResult shape:

~~~json
{
  "success": false,
  "tool": "pc.shell.powershell",
  "action": "pc.shell.powershell",
  "target": null,
  "summary": "pc.shell.powershell requires explicit approval before execution",
  "changed_files": [],
  "artifacts": [],
  "data": {},
  "logs": [],
  "warnings": ["No host application or PC control was invoked."],
  "error": "not_implemented",
  "reversible": true,
  "approval_level": 0,
  "duration_ms": null
}
~~~

Stable fields are success, tool, action, target, summary, changed_files, artifacts, data, logs, warnings, error, reversible, approval_level, and duration_ms. Permission levels follow the master plan: 0 read-only, 1 safe reversible, 2 potentially destructive, and 3 sensitive/privileged.

## Provider interface

Each PC, Blender, and SC2 provider implements health(), capabilities(), and invoke(action, target=None, parameters=None). PC is enabled only through the allowlisted native backend described below; Blender and SC2 still return not_implemented without external action.

## HTTP routes

| Method | Route | Purpose | Success behavior |
| --- | --- | --- | --- |
| GET | / | Service identity | 200 |
| GET | /health | Readiness summary | 200 if all ready, otherwise 503 |
| GET | /health/ready | Readiness probe | 200 if all ready, otherwise 503 |
| GET | /health/live | Process liveness | 200 without backend checks |
| GET | /api/v1/health | Versioned readiness summary | 200 if all ready, otherwise 503 |
| GET | /api/v1/tools | Provider/capability discovery | 200 |
| GET | /api/v1/runs | In-memory workflow runs | 200 |
| POST | /api/v1/chat | One-turn Hermes chat | 200 on model success, 503 if Qwen unavailable |
| GET | /api/v1/codex/health | Codex CLI readiness | 200 if available, otherwise 503 |
| GET | /api/v1/codex/runs | Recorded Codex handoffs | 200 |
| POST | /api/v1/codex/handoff | Approved repository coding handoff | 200 on success, 409 without approval |
| GET | /api/v1/pc/health | Controlled PC readiness | 200 on Windows, otherwise 503 |
| POST | /api/v1/pc/invoke | One allowlisted PC operation | 200 on success, 409 without approval |

Unknown routes return 404. Unsupported methods return 405.

## Chat request

POST /api/v1/chat accepts a JSON object:

~~~json
{
  "message": "Hello",
  "conversation_id": "optional-correlation-id",
  "task_type": "general",
  "system_prompt": "optional instruction"
}
~~~

message is required and non-empty. task_type defaults to general. conversation_id is a correlation value only; M1 does not persist history.

## Chat response

Successful and failed chats use the same structured response shape:

~~~json
{
  "success": true,
  "request_id": "generated-correlation-id",
  "conversation_id": "conversation-id",
  "message": {"role": "assistant", "content": "..."},
  "model": "qwen-local",
  "model_name": "qwen3.8:27b",
  "routing": {
    "task_type": "general",
    "selected_model": "qwen-local",
    "reason": "default_local_qwen",
    "fallback_model": null,
    "fallback_used": false
  },
  "usage": {},
  "latency_ms": 12,
  "warnings": [],
  "error": null
}
~~~

Invalid JSON or request fields return 400 with success=false, error=invalid_request, and details. An unavailable or invalid local Qwen backend returns 503 with a stable error code such as qwen_unavailable or qwen_invalid_json and a remediation warning. API keys are never included in responses or logs.

## Model routing

| task_type | selected model | reason | chat execution |
| --- | --- | --- | --- |
| repository_implementation | codex | task_requires_coding_specialist | fallback to qwen-local |
| difficult_debugging | codex | task_requires_coding_specialist | fallback to qwen-local |
| brainstorming | grok | task_requires_ideation_specialist | fallback to qwen-local |
| adversarial_review | grok | task_requires_critic_specialist | fallback to qwen-local |
| very_large_document | gemini-optional | task_requires_large_context_specialist | fallback to qwen-local |
| other / omitted | qwen-local | default_local_qwen | Qwen client |

Every chat logs model_selected and then model_fallback, model_failed, or chat_completed with request ID, selected model, reason, used model, outcome, and latency where available.

## Local Qwen transport

HttpQwenClient sends a non-streaming OpenAI-compatible request to the configured base URL:

~~~http
GET /models
POST /chat/completions
~~~

The default is http://127.0.0.1:11434/v1 with model qwen3.8:27b. Configure PERSONAL_AI_QWEN_BASE_URL, PERSONAL_AI_QWEN_MODEL, PERSONAL_AI_QWEN_TIMEOUT_SECONDS, PERSONAL_AI_QWEN_HEALTH_TIMEOUT_SECONDS, and optional PERSONAL_AI_QWEN_API_KEY. Context size is not part of the OpenAI-compatible request contract; explicit Ollama context profiles must be selected through a model alias or a future native Ollama transport.

## M2 Codex handoff

POST /api/v1/codex/handoff accepts:

~~~json
{
  "task_id": "optional-correlation-id",
  "repository_path": "D:/work/repository",
  "task": "Implement the requested change",
  "starting_revision": "optional-git-revision",
  "constraints": ["Do not commit changes"],
  "test_command": ["python", "-m", "pytest", "-q"],
  "test_timeout_seconds": 120,
  "approval_granted": true
}
~~~

The repository must be an existing Git root. The handoff rejects a stale starting revision, requires explicit approval, starts `codex exec` with `--ephemeral`, `--json`, and `--sandbox workspace-write`, and never commits or pushes. The service records the starting and ending revisions, dirty working-tree files, backend summary, test output, duration, and stable error code. Test commands are argv arrays and never run through a shell.

## M3 controlled PC operations

POST /api/v1/pc/invoke accepts:

~~~json
{
  "action": "pc.files.patch",
  "target": "working/file.txt",
  "parameters": {
    "approval_granted": true,
    "replacements": [{"old": "before", "new": "after"}]
  }
}
~~~

The native provider exposes the M3 actions for system/process inspection, allowlisted application launch/focus/close, workspace-bounded file read/copy/move/patch/snapshot, an allowlisted single PowerShell command, visible-window enumeration/focus, BMP screen capture, and keyboard/mouse fallback input. Relative and absolute file paths must resolve under PERSONAL_AI_PC_WORKSPACE_ROOT. Applications are limited by PERSONAL_AI_PC_ALLOWED_APPLICATIONS, defaulting to Notepad, Calculator, and Paint. PowerShell is launched without a shell wrapper and rejects command chaining, redirection, interpolation, absolute paths, and non-allowlisted verbs.

Permission levels are enforced at the provider boundary: read-only actions are automatic, safe reversible actions are level 1, and app close, file move/patch, PowerShell, and input actions are level 2 and require `approval_granted: true`. The service does not run as administrator and has no privileged-helper bypass. The live Notepad acceptance is opt-in via `scripts/pc-acceptance.ps1`; normal tests use deterministic fakes and never open applications.

## Workflow boundary

WorkflowService provides health() and list_runs() only. LangGraph state, checkpoints, human approval, pause/resume/cancel, retries, artifacts, and events are future contracts and are not implied by the empty run list.

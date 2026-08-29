# Tool contracts

M1 exposes read-only gateway routes plus Hermes local chat. PC, Blender, and SC2 capability names remain reserved discovery contracts and are not executable.

## Common result envelope

Future tool invocations must serialize the ToolResult shape:

~~~json
{
  "success": false,
  "tool": "pc.shell.powershell",
  "action": "pc.shell.powershell",
  "target": null,
  "summary": "pc.shell.powershell is defined but not implemented in M1",
  "changed_files": [],
  "artifacts": [],
  "logs": [],
  "warnings": ["No host application or PC control was invoked."],
  "error": "not_implemented",
  "reversible": true,
  "approval_level": 0,
  "duration_ms": null
}
~~~

Stable fields are success, tool, action, target, summary, changed_files, artifacts, logs, warnings, error, reversible, approval_level, and duration_ms. Permission levels follow the master plan: 0 read-only, 1 safe reversible, 2 potentially destructive, and 3 sensitive/privileged.

## Provider interface

Each PC, Blender, and SC2 provider implements health(), capabilities(), and invoke(action, target=None, parameters=None). In M1, health reports a ready skeleton, capabilities returns reserved names, and invoke returns not_implemented without external action.

## M1 HTTP routes

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

| task_type | selected model | reason | M1 execution |
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

The default is http://127.0.0.1:11434/v1 with model qwen3.8:27b. Configure PERSONAL_AI_QWEN_BASE_URL, PERSONAL_AI_QWEN_MODEL, PERSONAL_AI_QWEN_TIMEOUT_SECONDS, PERSONAL_AI_QWEN_HEALTH_TIMEOUT_SECONDS, and optional PERSONAL_AI_QWEN_API_KEY.

## Workflow boundary

WorkflowService provides health() and list_runs() only. LangGraph state, checkpoints, human approval, pause/resume/cancel, retries, artifacts, and events are future contracts and are not implied by the empty run list.

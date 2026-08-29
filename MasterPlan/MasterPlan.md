# PERSONAL AI PLATFORM — MASTER IMPLEMENTATION PLAN

## 1. Mission

Build a local-first personal AI platform capable of:

1. Conversational interaction through a custom web application.
2. Full controlled interaction with the Windows PC.
3. Local reasoning using Qwen as the default model.
4. Delegating serious coding work to Codex.
5. Using Grok for brainstorming, criticism, and alternative reasoning.
6. Supporting Gemini for very large-context/document workloads when appropriate.
7. Operating Blender programmatically and autonomously.
8. Creating and modifying StarCraft II maps/mods.
9. Running long-lived, resumable workflows.
10. Allowing remote monitoring and approvals from a phone.
11. Learning reusable procedures from successful work.
12. Maintaining complete observability, audit history, rollback, and artifacts.

The system must remain modular.

No individual model, framework, or UI should become impossible to replace later.

---

# 2. Core Architecture

Use the following conceptual architecture:

```text
                    CUSTOM WEB APP / PWA
                           |
                     Personal AI API
                           |
             +-------------+-------------+
             |                           |
          HERMES                     LANGGRAPH
    Conversational Agent          Workflow Engine
    Memory / Skills / Tools       Durable Execution
    Cron / Delegation             Checkpoints / HITL
             |                           |
             +-------------+-------------+
                           |
                     TOOL / MCP LAYER
                           |
          +----------------+----------------+
          |                |                |
          PC             Blender           SC2
          |                |                |
     Windows APIs       bpy / MCP      XML / Galaxy
     PowerShell         Headless       Editor / Files
     UI Automation      rendering
     Vision fallback
```

Models:

```text
DEFAULT GENERAL MODEL
    Qwen local

SERIOUS CODE DEVELOPMENT
    Codex

IDEATION / CRITIC / SECOND OPINION
    Grok

VERY LARGE CONTEXT / DOCUMENT TASKS
    Gemini when useful

ROUTINE LOCAL AUTOMATION
    Qwen
```

Do not tightly couple the architecture to any one model provider.

---

# 3. Fundamental Design Rule

Whenever controlling software:

```text
Structured API
    >
Application scripting API
    >
MCP tool
    >
Filesystem manipulation
    >
OS automation / accessibility
    >
Visual computer control
```

Mouse/keyboard visual automation must be the LAST fallback.

Examples:

Blender:
Use bpy/MCP before GUI clicking.

StarCraft II:
Modify structured map/mod files before interacting with Galaxy Editor visually.

Windows:
Use PowerShell/process APIs/UI Automation before visual clicking.

---

# 4. Repository Structure

Create a monorepo similar to:

```text
personal-ai/
│
├── apps/
│   └── web/
│
├── services/
│   ├── gateway/
│   ├── workflows/
│   ├── events/
│   └── privileged-helper/
│
├── integrations/
│   ├── pc/
│   ├── blender/
│   └── sc2/
│
├── agents/
│   ├── router/
│   ├── evaluator/
│   └── specialists/
│
├── skills/
│   ├── pc/
│   ├── blender/
│   ├── sc2/
│   └── general/
│
├── memory/
│   ├── semantic/
│   ├── episodic/
│   └── procedural/
│
├── policies/
│   ├── models.yaml
│   ├── tools.yaml
│   └── permissions.yaml
│
├── artifacts/
│
├── logs/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│
├── ARCHITECTURE.md
├── ROADMAP.md
├── STATUS.md
├── DECISIONS.md
├── NEXT.md
├── TOOL_CONTRACTS.md
└── README.md
```

---

# 5. Persistent Agent Handoff

The repository is the source of truth.

Do NOT rely on conversational memory for development state.

Maintain these files continuously:

## STATUS.md

Contains:

- what currently works;
- what is partially implemented;
- known failures;
- test status;
- active milestone.

## NEXT.md

Contains the next 3–10 concrete tasks.

## DECISIONS.md

Architecture Decision Records in concise form.

Example:

```text
ADR-003
Decision:
Blender modifications use bpy before computer vision.

Reason:
More deterministic and testable.

Date:
YYYY-MM-DD
```

## ROADMAP.md

Contains all milestones and their status.

## TOOL_CONTRACTS.md

Documents every tool exposed to agents.

At the end of every significant coding session:

1. run tests;
2. update STATUS.md;
3. update NEXT.md;
4. record architectural decisions;
5. commit changes when appropriate.

This protocol allows Codex, Hermes, Qwen, or another model to continue the project without needing the previous chat history.

---

# 6. Tool Contract Standard

All agent tools should expose structured inputs and outputs.

Example:

```json
{
  "success": true,
  "tool": "pc.launch_app",
  "target": "Blender",
  "changed_files": [],
  "artifacts": [],
  "warnings": [],
  "error": null,
  "reversible": true
}
```

Common return fields:

```text
success
tool
action
target
summary
changed_files
artifacts
logs
warnings
error
reversible
approval_level
duration
```

Do not make the models parse arbitrary terminal prose whenever structured information is possible.

---

# 7. Permission Model

Implement explicit permission levels.

## Level 0 — Read-only

Automatic.

Examples:

- inspect files;
- inspect processes;
- screenshots;
- read Blender scene;
- inspect SC2 map;
- query system status.

## Level 1 — Safe reversible modification

Automatic by default.

Examples:

- create workspace file;
- modify a working copy;
- launch an application;
- render Blender preview;
- create SC2 working copy.

## Level 2 — Potentially destructive

Require configurable approval.

Examples:

- delete files;
- terminate processes;
- install software;
- overwrite existing files;
- modify system configuration.

## Level 3 — Sensitive / privileged

Always require explicit approval.

Examples:

- administrator actions;
- credentials;
- purchases;
- external publication;
- Battle.net publishing;
- security configuration;
- destructive irreversible actions.

The main AI process should normally run without administrator privileges.

If privileged operations are needed, expose them through a small privileged helper with an allowlisted API.

Never expose unrestricted administrator shell access directly to an LLM.

---

# 8. Model Router

Start with deterministic routing rules.

Do NOT build a complicated AI router initially.

Example:

```text
if task == repository_implementation:
    Codex

elif task == difficult_debugging:
    Codex

elif task == brainstorming:
    Grok

elif task == adversarial_review:
    Grok

elif task == very_large_document:
    Qwen long-context or Gemini

else:
    Qwen
```

Later the router can learn from task history.

Model routing must be observable.

Every run should record:

```text
requested task
selected model
reason
fallback model
token usage when available
latency
success/failure
```

---

# 9. Evaluator Layer

Add lightweight outcome evaluation.

Do NOT make every response go through three models.

Use escalation.

Example:

```text
Qwen performs task
       |
   evaluator
       |
   +---+---+
   |       |
 good   uncertain
   |       |
 done   verify/escalate
```

Escalation examples:

```text
coding failure
    -> Codex

uncertain reasoning
    -> Grok critic

very large context
    -> Gemini

tool/action failure
    -> retry/recovery workflow
```

---

# 10. PC CONTROL LAYER

Goal:

Eventually provide complete controlled PC operation.

Expose tools such as:

```text
pc.system_info
pc.list_processes

pc.apps.list
pc.apps.launch
pc.apps.focus
pc.apps.close

pc.files.read
pc.files.copy
pc.files.move
pc.files.patch
pc.files.snapshot

pc.shell.powershell

pc.window.list
pc.window.focus

pc.screen.capture

pc.input.click
pc.input.drag
pc.input.type
pc.input.hotkey
pc.input.scroll
```

Prefer:

```text
PowerShell
Windows API
UI Automation
Hermes computer-use
```

before arbitrary coordinate-based clicking.

Every destructive action must pass through the permission policy.

---

# 11. BLENDER INTEGRATION

Blender is the FIRST major application integration.

The goal is to use Blender as the laboratory for:

- tool calling;
- visual feedback;
- artifacts;
- GPU jobs;
- workflow recovery;
- versioning;
- approvals;
- agent learning.

Primary control:

```text
Blender Python API (bpy)
MCP where useful
headless Blender CLI
```

Expose tools:

```text
blender.status
blender.open_file
blender.save_copy
blender.inspect_scene
blender.list_objects
blender.inspect_object
blender.import_asset
blender.export_asset
blender.execute_bpy

blender.material.create
blender.material.modify

blender.object.transform
blender.object.modify

blender.camera.configure

blender.render.preview
blender.render.final

blender.capture_viewport
```

Never modify the only copy of a source `.blend`.

Workflow:

```text
source
  |
snapshot
  |
working copy
  |
modification
  |
validation
  |
preview
  |
visual review
  |
final render
  |
new version
```

Configure GPU rendering appropriately for the local AMD GPU when supported.

Artifacts should include:

```text
.blend working version
render previews
final renders
exported models
logs
metadata
```

---

# 12. BLENDER LANGGRAPH WORKFLOW

Create a durable workflow:

```text
START
 |
snapshot_source
 |
inspect_scene
 |
understand_request
 |
plan_changes
 |
modify_scene
 |
validate_scene
 |
 +---- invalid ----> repair
 |
render_preview
 |
visual_evaluation
 |
 +---- rejected ----> revise
 |
optional_user_approval
 |
render_final
 |
save_version
 |
record_experience
 |
END
```

Requirements:

- checkpoint after major nodes;
- nodes should be idempotent where possible;
- workflow can resume after process failure;
- artifacts tied to run ID;
- user can pause/cancel;
- user can steer during execution.

---

# 13. STARCRAFT II INTEGRATION

SC2 is the SECOND major application integration.

Do not begin serious SC2 implementation until Blender automation is stable.

Primary methods:

```text
.SC2Map / .SC2Mod inspection
structured XML manipulation
Galaxy script
triggers
localization
actors
units
weapons
effects
upgrades
layouts
dependencies
```

Galaxy Editor GUI interaction is secondary.

Expose tools approximately like:

```text
sc2.project.inspect
sc2.project.snapshot
sc2.project.unpack
sc2.project.pack

sc2.search

sc2.unit.read
sc2.unit.modify

sc2.weapon.read
sc2.weapon.modify

sc2.effect.read
sc2.effect.modify

sc2.upgrade.read
sc2.upgrade.modify

sc2.actor.read
sc2.actor.modify

sc2.trigger.inspect
sc2.trigger.modify

sc2.galaxy.read
sc2.galaxy.patch
sc2.galaxy.validate

sc2.localization.read
sc2.localization.modify

sc2.editor.launch
sc2.map.test
sc2.test.collect_logs

sc2.package
```

Third-party SC2 tooling or MCP servers must be audited before integration.

Never let an unaudited external server receive unrestricted filesystem access.

---

# 14. SC2 LANGGRAPH WORKFLOW

Example:

```text
START
 |
snapshot_project
 |
index_project
 |
understand_request
 |
plan_change
 |
identify_dependencies
 |
patch_working_copy
 |
static_validation
 |
 +---- fail ----> diagnose_and_repair
 |
launch_test
 |
collect_results
 |
evaluate
 |
 +---- fail ----> diagnose -> patch -> retest
 |
optional_user_approval
 |
package_version
 |
record_experience
 |
END
```

Publishing externally must remain an approval-required action.

---

# 15. LANGGRAPH RESPONSIBILITY

LangGraph is NOT the conversational agent.

Use it when tasks:

- contain multiple dependent stages;
- take a long time;
- need retries;
- create artifacts;
- need checkpoints;
- need human approval;
- may survive process restart.

Examples:

```text
Blender model generation
SC2 map modification
large repository migration
complex PC maintenance
multi-stage media processing
```

Simple requests should remain directly in Hermes.

---

# 16. LANGGRAPH STATE

Each workflow should have explicit state.

Example:

```python
run_id
session_id
task
project_path
working_path

plan
current_step

artifacts
changed_files
warnings
errors

approval_required
approval_status

iteration

model_history
tool_history

started_at
updated_at
```

Development persistence may start simple.

Architecture must allow moving to a stronger persistent database later without redesigning workflows.

---

# 17. EVENT SYSTEM

Everything significant produces an event.

Examples:

```text
run.created
run.started

model.selected

tool.started
tool.completed
tool.failed

artifact.created

workflow.node.started
workflow.node.completed

approval.requested
approval.accepted
approval.rejected

run.completed
run.failed
run.cancelled
```

Events should power both:

- audit/history;
- live web application updates.

---

# 18. OBSERVABILITY

Every run should expose:

```text
run ID
session
task
model
workflow
status
started time
duration

current step
tools called
files changed
artifacts created
errors
warnings

approval state
```

Never allow autonomous activity that becomes invisible to the user.

---

# 19. MEMORY ARCHITECTURE

Use four conceptual memory categories.

## Working Memory

Current execution state.

## Semantic Memory

Stable knowledge.

Examples:

```text
project directory
tool preferences
application configuration
SC2 project architecture
```

## Episodic Memory

What happened.

Example:

```text
Attempted Blender export.
Normals became inverted.
Applying transforms before export fixed it.
```

## Procedural Memory

Reusable validated procedures.

Example:

```text
skill:
blender_to_sc2_export
```

---

# 20. LEARNING / SKILL PROMOTION

Do NOT automatically rewrite skills after one successful task.

Use:

```text
experience
   |
pattern detection
   |
candidate procedure
   |
test
   |
repeat validation
   |
promote to skill
```

A failed candidate must not corrupt the stable skill.

Version skills:

```text
skill v1
skill v2 candidate
skill v2 validated
```

Record provenance:

```text
what experiences generated it
who/what generated it
tests performed
success rate
last validated date
```

---

# 21. CUSTOM WEB APPLICATION

Eventually the custom web application becomes the main user interface.

Recommended conceptual stack:

```text
Frontend:
React / Next.js PWA

Backend:
FastAPI-style API gateway

Streaming:
SSE initially
WebSocket only where actually needed

Remote access:
private secure network such as Tailscale

Do not expose raw Hermes endpoints publicly.
```

The API gateway mediates between:

```text
web UI
Hermes
LangGraph workflows
event store
artifacts
system metrics
```

---

# 22. WEB APP PAGES

## Chat

Chat with the agent.

Show tool activity inline.

Example:

```text
User:
Create another mechanical Protoss Immortal.

Agent:
Planning...

Tool: Blender
Inspecting scene...

Render preview:
[image]
```

---

## Runs

Display:

```text
running jobs
queued jobs
completed jobs
failed jobs
paused jobs
```

Each run shows progress.

---

## Approvals

Example:

```text
SC2 workflow wants to modify:

Marine.xml
Upgrade.xml
Weapon.xml

[View diff]

Approve
Reject
Modify instruction
```

---

## Artifacts

Browse:

```text
renders
.blend versions
SC2 map versions
logs
reports
screenshots
exports
```

---

## Models

Display:

```text
Qwen
loaded/unloaded
context
VRAM/RAM

Codex
availability

Grok
connection state

Gemini
connection state
```

---

## System

Display:

```text
CPU
RAM
GPU
VRAM
disk
active applications

workflow service
Hermes
local model
Blender
SC2
```

---

# 23. MOBILE REQUIREMENTS

The web application must work comfortably from a phone.

Primary mobile actions:

```text
chat
view run progress
see screenshots/previews
approve/reject actions
send steering instruction
pause
resume
cancel
view artifacts
```

Do not design mobile as an afterthought.

Use responsive design from the beginning.

---

# 24. REMOTE ACCESS

Initial remote-access model:

```text
Phone
  |
Private VPN / Tailscale
  |
Home PC
  |
Personal AI Gateway
```

Do not directly expose:

```text
Hermes
Qwen server
Blender MCP
SC2 MCP
privileged helper
```

to the public Internet.

Only the gateway should be reachable by the UI.

---

# 25. OPTIONAL MULTI-AGENT LAYER

Do NOT implement multi-agent infrastructure initially.

Hermes delegation is sufficient first.

If genuine multi-agent coordination becomes necessary later, evaluate Microsoft Agent Framework rather than starting a new AutoGen architecture.

Example future workflow:

```text
SC2 Supervisor
      |
 +----+----------------+
 |         |           |
Design   Blender    SC2 Data
Agent     Agent       Agent
 |         |           |
 +---------+-----------+
           |
          QA
```

Only add this after there are real tasks that require it.

---

# 26. DEVELOPMENT MILESTONES

## M0 — Foundation

Deliver:

- repository;
- Python environment;
- base configuration;
- lint/format/test setup;
- logging;
- architecture docs;
- status/handoff docs.

Acceptance:

```text
fresh clone can run development checks
tests execute
configuration has safe defaults
documentation explains how to start
```

---

## M1 — Local AI

Deliver:

- Hermes working;
- local Qwen connection;
- basic model router;
- local test chat.

Acceptance:

```text
user can talk to Hermes
Qwen answers locally
model selection is logged
```

---

## M2 — Codex Integration

Deliver:

- clean Codex handoff;
- coding tasks can be delegated;
- results return to main system;
- code changes remain observable.

Acceptance:

```text
Hermes can hand a repository coding task to Codex
Codex modifies a test repository
tests run
changes are summarized
```

---

## M3 — PC Control

Deliver structured:

```text
launch application
list/focus window
PowerShell command
filesystem working-copy support
screenshot
keyboard/mouse fallback
```

Acceptance test:

```text
agent opens Notepad
creates a controlled test file
types known text
saves it
verifies file contents
closes application
```

All operations must be logged.

---

## M4 — Permission System

Deliver:

- permission levels;
- approval requests;
- allowlists;
- privileged-helper boundary.

Acceptance:

```text
safe action executes automatically
destructive action pauses for approval
privileged action cannot bypass policy
```

---

## M5 — Blender Bridge

Deliver:

- inspect scene;
- execute controlled bpy;
- create working copies;
- render preview;
- save artifacts.

Acceptance:

Agent can:

```text
open test .blend
duplicate working file
modify cube
change material
position camera
render image
save new .blend
```

without mouse interaction.

---

## M6 — Blender Autonomous Workflow

Deliver:

```text
snapshot
plan
modify
validate
render
evaluate
revise
finalize
```

Acceptance:

A natural-language request produces a modified Blender scene and render while preserving the original.

---

## M7 — LangGraph Durable Blender Workflow

Deliver:

- checkpoints;
- retry;
- recovery;
- pause;
- resume;
- cancel;
- human approval.

Acceptance:

Kill workflow halfway through.

Restart services.

Workflow resumes without restarting from step one.

---

## M8 — SC2 Inspection

Deliver:

- safe SC2 project snapshot;
- parser/indexer;
- search;
- read units/weapons/upgrades;
- no modifications initially.

Acceptance:

Agent can explain where a chosen Marine stat comes from and identify related data dependencies.

---

## M9 — SC2 Modification

Deliver working-copy modification.

Acceptance:

Modify a harmless known map parameter and validate the project without altering the original.

---

## M10 — SC2 Test Loop

Deliver:

```text
patch
validate
launch
test
collect result
diagnose
```

Acceptance:

Agent successfully changes a controlled map property and verifies the modified map through the test workflow.

---

## M11 — LangGraph SC2 Workflow

Add:

```text
durability
checkpoints
retries
approval
artifacts
version history
```

---

## M12 — Experience Memory

Store successful/failed execution episodes.

Acceptance:

Agent can answer:

```text
What failed last time we exported this type of Blender model?
```

using recorded project history.

---

## M13 — Skill Learning

Implement:

```text
experience
candidate
validation
promotion
versioning
```

Acceptance:

Repeated successful procedure becomes a candidate skill but does not replace stable behavior automatically.

---

## M14 — Web Gateway

Expose controlled API for:

```text
chat
runs
events
approvals
artifacts
status
```

---

## M15 — Web Chat

Build mobile-compatible chat.

---

## M16 — Monitoring Dashboard

Display:

```text
runs
tools
models
system usage
workflows
artifacts
```

---

## M17 — Mobile Approvals

Allow user to:

```text
approve
reject
steer
pause
resume
cancel
```

from phone.

---

## M18 — Secure Remote Access

Configure private remote access.

No public raw agent services.

---

## M19 — Scheduled / Autonomous Jobs

Integrate recurring work only after permissions, observability, and recovery are proven.

---

## M20 — Multi-Agent Expansion

Only implement if real workload demonstrates a need.

---

# 27. CODING STRATEGY

Codex should NOT attempt to implement this entire roadmap in one session.

Use incremental milestones.

Each coding cycle:

```text
1. Read:
   ARCHITECTURE.md
   STATUS.md
   NEXT.md
   DECISIONS.md

2. Select one bounded task.

3. Inspect relevant code.

4. Implement.

5. Add/update tests.

6. Run tests.

7. Update documentation.

8. Update STATUS.md.

9. Update NEXT.md.

10. Stop.
```

Do not continue recursively implementing unrelated future milestones.

---

# 28. AI DEVELOPMENT RESPONSIBILITY

Use Codex primarily for:

```text
architecture
critical infrastructure
complex repository changes
LangGraph implementation
security-sensitive code
initial MCP/tool integrations
difficult bugs
refactors
integration tests
code reviews
```

Use Hermes + local Qwen for:

```text
operating finished tools
investigating logs
creating skills
routine configuration
documentation updates
workflow execution
data inspection
simple repetitive scripts
project organization
Blender tasks after bridge exists
SC2 tasks after bridge exists
```

Local Qwen may implement low-risk repetitive glue code once clear patterns and tests exist.

Codex should remain available for review/escalation.

---

# 29. TOKEN / COST EFFICIENCY

The architecture must reduce dependence on expensive/cloud coding context.

Rules:

1. Put persistent knowledge in repository files.
2. Keep tasks small.
3. Avoid repeatedly explaining the entire project to Codex.
4. Codex reads STATUS/NEXT instead.
5. Use local model for log analysis.
6. Use local model for documentation extraction.
7. Use Codex when coding quality matters.
8. Keep tool contracts stable.
9. Add tests so local models can safely make low-risk changes.
10. Automatically summarize long execution histories into project memory.

---

# 30. INITIAL SUCCESS TARGET

The first major demonstration should be:

User says:

```text
Create a new version of this Blender model,
make the armor more mechanical,
generate front, side, rear, and perspective renders.
```

System:

```text
creates working copy
understands scene
modifies model
renders preview
evaluates output
revises if required
generates final images
stores artifacts
preserves original
reports changes
```

Second major demonstration:

User says:

```text
Take this approved model and integrate it into
the SC2 test mod.
```

System:

```text
creates SC2 working version
exports required asset
adds/updates data
validates dependencies
launches test
captures result
reports success/failure
stores version
```

---

# 31. FINAL PRODUCT EXPERIENCE

From the phone:

```text
User:
Nexus, create another Protoss Immortal based on the
previous design, but make it more mechanical.
Generate four views and then integrate it into the SC2 mod.
```

Expected system behavior:

```text
Hermes
 |
recall relevant project context
 |
plan
 |
start durable Blender workflow
 |
generate and visually evaluate model
 |
request approval if appropriate
 |
start SC2 integration workflow
 |
validate
 |
test
 |
produce final artifacts
```

Phone UI:

```text
✓ Blender model created
✓ 4 renders generated
✓ Visual validation passed
✓ SC2 asset imported
✓ Data dependencies valid
✓ Test map launched

[View renders]
[View SC2 test]
[Approve version]
[Request changes]
```

This is the target architecture.

Do not sacrifice modularity, recoverability, observability, safety, or deterministic tooling merely to make an early demo appear more autonomous.
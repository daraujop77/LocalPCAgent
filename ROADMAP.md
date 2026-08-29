# Roadmap

Status is intentionally conservative. Only M0 is in scope for the first development cycle.

| Milestone | Status | Scope |
| --- | --- | --- |
| M0 — Foundation | Complete | Repository, Python tooling, contracts, safe skeletons, health, tests, handoff docs |
| M1 — Local AI | Planned | Hermes, local Qwen connection, deterministic model router, local test chat |
| M2 — Codex Integration | Planned | Observable Codex handoff and test-repository coding loop |
| M3 — PC Control | Planned | Structured Windows app/filesystem/process/screenshot operations |
| M4 — Permission System | Planned | Approvals, allowlists, privileged-helper boundary |
| M5 — Blender Bridge | Planned | bpy/MCP inspection, working copies, preview render, artifacts |
| M6 — Blender Autonomous Workflow | Planned | Snapshot, plan, modify, validate, render, evaluate, finalize |
| M7 — Durable Blender Workflow | Planned | LangGraph checkpoints, retry, recovery, pause/resume/cancel |
| M8 — SC2 Inspection | Planned | Safe project snapshot, parser/indexer, search, read-only data inspection |
| M9 — SC2 Modification | Planned | Working-copy structured modifications and validation |
| M10 — SC2 Test Loop | Planned | Patch, validate, launch, collect results, diagnose |
| M11 — Durable SC2 Workflow | Planned | Durability, checkpoints, retries, approvals, artifacts, version history |
| M12 — Experience Memory | Planned | Successful and failed execution episodes |
| M13 — Skill Learning | Planned | Candidate procedures, validation, promotion, versioning |
| M14 — Web Gateway | Planned | Controlled API for chat, runs, events, approvals, artifacts, status |
| M15 — Web Chat | Planned | Responsive mobile-compatible chat |
| M16 — Monitoring Dashboard | Planned | Runs, tools, models, system usage, workflows, artifacts |
| M17 — Mobile Approvals | Planned | Approve, reject, steer, pause, resume, cancel from phone |
| M18 — Secure Remote Access | Planned | Private-network access with no public raw agent services |
| M19 — Scheduled / Autonomous Jobs | Planned | Recurring work after permissions, observability, and recovery |
| M20 — Multi-Agent Expansion | Planned | Add only if real workload proves it necessary |

## Sequencing constraints

- Do not start M1 in this cycle.
- Do not begin serious SC2 work before Blender automation is stable.
- Do not add multi-agent infrastructure before real workload demonstrates a need.
- Do not expose raw Hermes, Qwen, Blender MCP, SC2 MCP, or the privileged helper publicly.


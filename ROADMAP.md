# Roadmap

Status is intentionally conservative. M0 through M13 have bounded local implementations; live application validation and later product surfaces remain planned.

| Milestone | Status | Scope |
| --- | --- | --- |
| M0 — Foundation | Complete | Repository, Python tooling, contracts, safe skeletons, health, tests, handoff docs |
| M1 — Local AI | Complete | Hermes boundary, local Qwen client, deterministic router, local chat, model-selection logging, live Ollama/qwen3.8:27b acceptance |
| M2 — Codex Integration | Complete | Approved observable Codex CLI handoff, working-tree observation, and post-handoff tests |
| M3 — PC Control | Complete | Allowlisted Windows app/filesystem/process/window/screenshot/input operations |
| M4 — Permission System | Complete | Central levels, scoped one-time approvals, validated allowlists, fail-closed privileged-helper boundary |
| M5 — Blender Bridge | Implemented (bounded) | Headless CLI/JSON fixture inspection, working copies, controlled bpy boundary, preview artifacts |
| M6 — Blender Autonomous Workflow | Implemented (bounded) | Snapshot, inspect, modify, validate, preview, and experience-recording graph |
| M7 — Durable Blender Workflow | Implemented (graph-compatible) | JSON checkpoints, events, retry, recovery, pause/resume/cancel |
| M8 — SC2 Inspection | Implemented (structured) | Safe project snapshot, directory/ZIP inspection, search, XML/Galaxy reads |
| M9 — SC2 Modification | Implemented (working-copy) | Approval-gated structured text patching and validation |
| M10 — SC2 Test Loop | Implemented (static) | Patch, validate, package, and structured result collection; game launch remains disabled |
| M11 — Durable SC2 Workflow | Implemented (graph-compatible) | Checkpoints, events, retries, pause/resume/cancel, artifacts, version history |
| M12 — Experience Memory | Implemented (JSON stores) | Semantic facts and successful/failed execution episodes |
| M13 — Skill Learning | Implemented (explicit promotion) | Candidate procedures, repeated validation, provenance, versioned promotion |
| M14 — Web Gateway | Planned | Controlled API for chat, runs, events, approvals, artifacts, status |
| M15 — Web Chat | Planned | Responsive mobile-compatible chat |
| M16 — Monitoring Dashboard | Planned | Runs, tools, models, system usage, workflows, artifacts |
| M17 — Mobile Approvals | Planned | Approve, reject, steer, pause, resume, cancel from phone |
| M18 — Secure Remote Access | Planned | Private-network access with no public raw agent services |
| M19 — Scheduled / Autonomous Jobs | Planned | Recurring work after permissions, observability, and recovery |
| M20 — Multi-Agent Expansion | Planned | Add only if real workload proves it necessary |

## Sequencing constraints

- M2 and M3 were implemented together after explicit instruction; M1 live-chat acceptance is verified against the local Ollama/qwen3.8:27b backend.
- M2 handoffs do not commit or push. M3 host control remains local, allowlisted, workspace-bounded, and non-admin. M4 centrally gates level-2/3 actions with scoped one-time approvals.
- Do not begin serious SC2 work before Blender automation is stable.
- Do not add multi-agent infrastructure before real workload demonstrates a need.
- Do not expose raw Hermes, Qwen, Blender MCP, SC2 MCP, or the privileged helper publicly.
- M5-M13 live Blender rendering requires a configured Blender executable. SC2 `.SC2Map`/`.SC2Mod` support is limited to directories and ZIP-compatible fixtures; MPQ/game/editor execution requires a future audited adapter.
- The workflow engine persists a stable graph-compatible shape without requiring LangGraph at runtime; a LangGraph adapter can be added without changing the API or stored state contract.

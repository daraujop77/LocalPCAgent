# Roadmap

Status is intentionally conservative. M0 through M4 are complete foundations. M5 through M13 are bounded local foundations with live application and full autonomy gaps called out below. M14 through M17 are bounded gateway/UI foundations; secure remote access and live product integrations remain planned.

| Milestone | Status | Scope |
| --- | --- | --- |
| M0 — Foundation | Complete | Repository, Python tooling, contracts, safe skeletons, health, tests, handoff docs |
| M1 — Local AI | Complete | Hermes boundary, local Qwen client, deterministic router, local chat, model-selection logging, live Ollama/qwen3.8:27b acceptance |
| M2 — Codex Integration | Complete | Approved observable Codex CLI handoff, working-tree observation, and post-handoff tests |
| M3 — PC Control | Complete | Allowlisted Windows app/filesystem/process/window/screenshot/input operations |
| M4 — Permission System | Complete | Central levels, scoped one-time approvals, validated allowlists, fail-closed privileged-helper boundary |
| M5 — Blender Bridge | Foundation complete | Headless CLI/JSON fixture inspection, artifact-root working copies, controlled bpy boundary, preview artifacts; live Blender remains environment-dependent |
| M6 — Blender Autonomous Workflow | Partial | Explicit operation planning, validation, preview evaluation, revision hook, finalization; natural-language planning and visual revision remain planned |
| M7 — Durable Blender Workflow | Foundation complete | Atomic JSON checkpoints, event replay, interruption recovery, retry, pause/resume/cancel; LangGraph is not the default executor yet |
| M8 — SC2 Inspection | Foundation complete | Safe directory/ZIP inspection, search, XML/structured reads, entity/field index; MPQ-native parsing and full dependency resolution remain planned |
| M9 — SC2 Modification | Foundation complete | Approval-gated text patching only inside managed working copies, validation, packaging |
| M10 — SC2 Test Loop | Partial | Static patch/validate/package/log contracts; Galaxy Editor/game launch and real verification remain disabled |
| M11 — Durable SC2 Workflow | Foundation complete | Shared durable workflow/checkpoint/event/artifact boundaries; LangGraph migration and live test recovery remain planned |
| M12 — Experience Memory | Foundation complete | Semantic/episodic stores, token-scored history lookup, Hermes context injection |
| M13 — Skill Learning | Foundation complete | Repeated successful procedure candidate suggestions, provenance, explicit validation and promotion |
| M14 — Web Gateway | Foundation complete | Bearer/CORS/CSRF socket edge, filtered pagination, SSE event replay, artifact metadata/download boundary |
| M15 — Web Chat | Foundation complete | Dependency-free mobile PWA shell for chat, runs, approvals, artifacts, and system status |
| M16 — Monitoring Dashboard | Foundation complete | PWA monitoring cards for runs, tools, workflows, models, system usage, and artifacts |
| M17 — Mobile Approvals | Foundation complete | Mobile run pause/resume/retry/cancel controls and approval accept/reject controls |
| M18 — Secure Remote Access | Planned | Private-network access with no public raw agent services |
| M19 — Scheduled / Autonomous Jobs | Planned | Recurring work after permissions, observability, and recovery |
| M20 — Multi-Agent Expansion | Planned | Add only if real workload proves it necessary |

## Sequencing constraints

- M2 and M3 were implemented together after explicit instruction; M1 live-chat acceptance is verified against the local Ollama/qwen3.8:27b backend.
- M2 handoffs do not commit or push. M3 host control remains local, allowlisted, workspace-bounded, and non-admin. M4 centrally gates level-2/3 actions with scoped one-time approvals.
- Do not begin serious SC2 work before Blender automation is stable.
- Do not add multi-agent infrastructure before real workload demonstrates a need.
- Do not expose raw Hermes, Qwen, Blender MCP, SC2 MCP, or the privileged helper publicly.
- M5-M6 live Blender modification/rendering requires a configured Blender executable and an explicit structured operation plan. Natural-language planning, visual evaluation, and automatic revision require a future model/evaluator boundary.
- SC2 `.SC2Map`/`.SC2Mod` support is limited to directories and ZIP-compatible fixtures; MPQ-native parsing, Galaxy compiler integration, and game/editor execution require future audited adapters.
- The workflow engine persists a stable graph-compatible shape and automatically recovers interrupted runs, but the optional LangGraph adapter is not the default executor until migration and crash tests exist.
- M14 authentication is token-based and intentionally simple for a private/local boundary. Durable identity, durable approvals, frontend PWA, Tailscale policy, and public deployment remain future milestones.

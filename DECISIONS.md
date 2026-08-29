# Architecture decisions

## ADR-001 — Use the plan-defined monorepo at the repository root

Decision: Keep apps, services, integrations, agents, skills, memory, policies, artifacts, logs, tests, and docs at the root, with the shared installable Python package under src/personal_ai.

Reason: This preserves the master plan's ownership boundaries while giving shared Python code a conventional package layout for editable installs and future service extraction.

Date: 2026-08-29

## ADR-002 — Keep M0 runtime dependencies in the standard library

Decision: Use http.server, dataclasses, environment configuration, and standard-library logging for the M0 runtime. Declare pytest and Ruff as development dependencies.

Reason: The inspected Windows host has Python 3.12 but no Node.js, and M0 required foundation and health checks rather than a production web framework.

Date: 2026-08-29

## ADR-003 — Expose integration contracts before enabling control

Decision: PC, Blender, and SC2 providers expose health, capability discovery, and structured not_implemented results only. No host-control or mutation endpoint exists in M0 or M1.

Reason: The master plan requires explicit interfaces, structured tools, GUI automation as a fallback, and no unrestricted PC control.

Date: 2026-08-29

## ADR-004 — Bind locally by default

Decision: The gateway binds to loopback unless PERSONAL_AI_ALLOW_REMOTE=true is explicitly configured. No public exposure or private-network setup is included in M1.

Reason: The platform is local-first and raw agent services must not be exposed publicly.

Date: 2026-08-29

## ADR-005 — Keep handoff documents as operational state

Decision: ARCHITECTURE.md, STATUS.md, NEXT.md, DECISIONS.md, TOOL_CONTRACTS.md, and ROADMAP.md are maintained at every milestone boundary.

Reason: Future Codex, Hermes, and local-Qwen sessions must continue without relying on previous conversation context.

Date: 2026-08-29

## ADR-006 — Keep Hermes separate from the model provider

Decision: HermesService owns chat validation, routing, correlation, response shaping, and outcome logging. ModelClient owns model transport. M1 does not embed provider-specific logic in Hermes.

Reason: Hermes is the conversational harness and Qwen is replaceable. This keeps Codex, Grok, Gemini, and future local backends attachable without changing the chat contract.

Date: 2026-08-30

## ADR-007 — Use an OpenAI-compatible local HTTP boundary for Qwen

Decision: HttpQwenClient uses GET /models for health and POST /chat/completions for non-streaming generation. The default endpoint is http://127.0.0.1:11434/v1, with endpoint and model configurable by environment.

Reason: It supports common local runtimes such as Ollama-style servers without coupling M1 to an SDK or vendor-specific client.

Date: 2026-08-30

## ADR-008 — Route deterministically and fall back visibly

Decision: ModelRouter uses explicit task_type rules. M1 selects Qwen for ordinary chat and falls back to Qwen for specialist categories whose providers are not yet wired. Responses and logs retain the requested route, reason, fallback model, and fallback_used flag.

Reason: The master plan calls for observable routing and explicitly defers a complicated learned router. Visible fallback preserves a working local chat without hiding unavailable specialists.

Date: 2026-08-30

## ADR-009 — Use qwen3.5:9b as the M1 local default

Decision: Use qwen3.5:9b as the repository and Hermes default local model. Keep qwen3:8b installed as an optional smaller model, but do not advertise it as the M1 Hermes default.

Reason: Ollama reports qwen3:8b with a 40K context window, below the installed Hermes Agent's 64K minimum. Ollama reports qwen3.5:9b with a 256K context window, and the model fits the inspected host's available memory/storage envelope.

Date: 2026-08-30

## ADR-010 — Use qwen3.8:27b as the M1 local default

Decision: Use qwen3.8:27b as the repository and Hermes default local model. Keep qwen3:8b and qwen3.5:9b installed as optional local models, but do not advertise them as the M1 default. Do not pull qwen3.8-flash-next:125b-mlx on this Windows/AMD host.

Reason: The requested qwen3.8:27b model is available through Ollama, reports a 256K context window, and meets Hermes's 64K minimum. The Flash-Next preview is an MLX-oriented 125B model with approximately 113 GB of local data, which is not a practical target for this host's Windows/AMD runtime.

Date: 2026-08-29

## ADR-011 — Prefer 64K for Qwen3.8 and use Qwen3 8B for light tasks

Decision: Treat a 64K Qwen3.8:27B runtime profile as the recommended primary operating point. Keep 128K available for explicit long-context requests only. Use the already-installed qwen3:8b as the light-task candidate at a 32K profile; do not make it the Hermes default because its published context window is below the 64K Hermes baseline.

Reason: Both Qwen3.8 profiles completed on the Windows/AMD host, but the 128K profile reduced warm short-request speed from 228 ms to 1,195 ms, moved approximately 2.3 GB of loaded model footprint off VRAM, and increased peak private process memory from 21.16 GB to 23.05 GB. qwen3:8b completed the light-task check in 127 ms warm with 9.64 GB peak private process memory. The benchmark used a short prompt, so 128K remains an explicit capacity option rather than a claim about full-document quality.

Date: 2026-08-29

## ADR-012 — Make Codex handoffs explicit, observable, and uncommitted

Decision: Add a CodexHandoffService with a replaceable backend. A handoff requires an existing Git root, may pin a starting revision, requires explicit approval, runs the configured Codex CLI in an ephemeral workspace-write sandbox, runs an argv test command without a shell, records dirty files and results, and never commits or pushes.

Reason: M2 needs a clean boundary between Hermes and serious repository work while keeping changes inspectable and preventing an agent handoff from becoming an invisible or automatically published mutation.

Date: 2026-08-29

## ADR-013 — Implement M3 PC control as an allowlisted native provider

Decision: Enable only a controlled NativeWindowsPcControl backend. File paths are bounded to a configured workspace, applications are executable-name allowlisted, PowerShell is restricted to a small single-command verb set, and potentially disruptive actions require central authorization. Windows APIs are preferred for windows, screenshots, and input; GUI automation remains a fallback. The provider never elevates or exposes arbitrary process termination.

Reason: M3 requires useful Windows control, but the platform must remain local-first, non-admin, and safe from unrestricted PC control. A replaceable backend also keeps normal tests deterministic and avoids opening applications during CI.

Date: 2026-08-29

## ADR-014 — Centralize permissions and allowlists in one validated policy

Decision: Load exact action levels, PC application/PowerShell allowlists, approval TTL, non-admin constraints, and privileged-helper settings from `policies/permissions.yaml`. The file uses JSON-compatible YAML and is parsed with the Python standard library. Gateway startup fails if the policy is invalid.

Reason: PC and Codex must not develop independent approval rules. A checked-in, dependency-free, fail-fast policy is inspectable by future agents and keeps environment variables from silently changing the security model.

Date: 2026-08-29

## ADR-015 — Make approvals exact-scope, expiring, and one-time

Decision: Bind each level-2/3 approval to a canonical digest of action, target, and sanitized parameters. Accepted approvals expire, cannot change scope, and are consumed before backend execution. Boolean approval fields are ignored as authorization. M4 stores requests and audit events in process memory.

Reason: A generic or reusable approval token could authorize a different destructive action. Exact scope and one-time consumption limit replay while the process-local implementation provides the M4 contract without pretending durability exists.

Date: 2026-08-29

## ADR-016 — Define but do not activate the privileged helper

Decision: Add an importable helper service/backend protocol with a disabled default backend. Level-3 policy approval is necessary but never sufficient: helper configuration and action allowlisting must also pass. No elevated executable, installer, named-pipe server, or privileged operation is implemented in M4.

Reason: The main AI service must remain non-administrator, and a placeholder helper must not become an accidental bypass. A fail-closed interface lets later work add an audited transport without weakening the current boundary.

Date: 2026-08-29

## ADR-017 — Route explicit coding handoffs through Hermes

Decision: Keep coding handoffs explicit and structured, but make Hermes the conversational owner of the `delegate_to_codex` boundary. Ordinary chat continues to use Qwen; only a validated handoff request can reach Codex and it remains subject to the central approval policy.

Reason: The M2 acceptance requires Hermes to hand repository work to Codex. A separate gateway endpoint is useful for clients, but it must not bypass the conversational orchestration boundary.

Date: 2026-08-29

## ADR-018 — Use structured PowerShell argv with trusted executable resolution

Decision: PC application launch accepts only bare allowlisted names mapped at startup to resolved executable paths. PowerShell accepts an allowlisted verb and string arguments, quotes values into a fixed invocation, rejects expansion/injection syntax, and resolves path arguments under the PC workspace. Timeouts become structured provider failures.

Reason: Basename-only executable checks and free-form script inspection allowed path and expansion bypasses. Structured arguments reduce injection surface while retaining a narrow Windows fallback capability.

Date: 2026-08-29

## ADR-019 — Report Codex deltas against a content baseline

Decision: Capture a repository file-content baseline immediately before an approved Codex backend starts. Return `preexisting_files` separately and calculate `changed_files` from the before/after content maps.

Reason: Git status after execution cannot distinguish a user edit that existed before handoff from a Codex change to the same path. Baseline comparison makes the observable result useful without requiring a clean checkout.

Date: 2026-08-29

## ADR-020 — Keep Blender execution headless and working-copy based

Decision: Implement the Blender provider behind a replaceable backend. JSON scene fixtures support deterministic tests; a configured Blender executable is invoked only in background mode for `.blend` work. Mutations target a copied working file and accept structured allowlisted operations rather than free-form Python. GUI automation remains a fallback and is not enabled.

Reason: The primary Blender interface is `bpy`/MCP, but the main service must remain local, observable, non-admin, and safe from source-file destruction. A backend protocol allows a future audited MCP adapter without changing the gateway contract.

Date: 2026-08-29

## ADR-021 — Treat SC2 projects as structured working copies

Decision: Implement SC2 inspection and modification over bounded directories and ZIP-compatible project fixtures. Reads are automatic; snapshots, packaging, and text modifications use policy levels. XML/Galaxy validation is deterministic and conservative. Galaxy Editor and game launch remain disabled until a real tool is audited.

Reason: Structured project files are the primary interface described by the master plan, while unaudited editor/game automation could expose broad filesystem or process control. The first bridge should be useful without pretending to support every proprietary archive format.

Date: 2026-08-29

## ADR-022 — Persist workflows as graph-compatible JSON checkpoints

Decision: Use explicit named nodes, JSON-compatible state, per-node checkpoints, JSONL lifecycle events, and run controls for pause/resume/retry/cancel/steer. Do not require LangGraph at runtime until an adapter can preserve the stored run and event contracts.

Reason: M7 and M11 need recovery and observability immediately, but a dependency-heavy graph runtime should not become a hidden source of migration breakage. The stable state shape can later be backed by LangGraph or a database.

Date: 2026-08-29

## ADR-023 — Separate experience recording from skill promotion

Decision: Store semantic facts, append-only execution episodes, and versioned procedural skills separately. Candidate procedures retain episode provenance, require repeated explicit validation, and must be explicitly promoted. Failed candidates never replace promoted versions.

Reason: One successful run is not enough evidence for an autonomous skill. Separate stores preserve auditability and make learning reversible and reviewable.

Date: 2026-08-29

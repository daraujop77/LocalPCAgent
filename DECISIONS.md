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

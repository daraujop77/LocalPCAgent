# Events service boundary

The generic cross-service event store remains planned. Workflow lifecycle events are currently persisted by `services/workflows` as JSONL and exposed through the M14 run-scoped replay/SSE boundary.

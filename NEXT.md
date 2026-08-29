# Next tasks

M5–M13 bounded local implementations are complete. Do not begin M14 without explicit instruction.

## M14 — Web Gateway

1. Define the authenticated PWA-facing API version and origin/CSRF policy while keeping raw Hermes, Qwen, Blender, SC2, and privileged-helper services private.
2. Add durable event streaming (SSE initially) from the workflow event store with run-scoped filtering and reconnect support.
3. Add artifact metadata/download contracts with content-type, size, provenance, and access checks.
4. Add API pagination and filters for runs, approvals, events, artifacts, memory episodes, and skills.
5. Add an integration test matrix for the web gateway against loopback and a private-network configuration; keep remote binding disabled by default.

## Deferred live validation

- Configure a supported Blender executable and run the opt-in headless fixture acceptance against a copied `.blend` file.
- Validate the SC2 bridge against a real project format; add an audited MPQ/Galaxy tool adapter before enabling editor/game launch.
- Evaluate an optional LangGraph adapter against the persisted `WorkflowRun` and event contracts; do not replace the stable local runner without migration tests.
- Add durable authenticated approvals before exposing any approval route beyond loopback/private network.

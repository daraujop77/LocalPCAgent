# Next tasks

M14–M17 bounded gateway/PWA foundations are complete for this cycle. Continue with M18 only when explicitly requested.

## M18 — Secure Remote Access

1. Define the private-network deployment target (Tailscale or equivalent) and allowed network identity model.
2. Add an explicit remote bind policy that cannot expose raw Hermes, Qwen, Blender, SC2, or privileged-helper services.
3. Add integration tests for loopback, authenticated private-network requests, rejected origins, and missing-token startup.
4. Document key rotation, token storage, and the rollback path to loopback-only mode.

## Deferred platform validation

- Configure a supported Blender executable and run the opt-in headless acceptance against a copied `.blend` file, including real controlled bpy operations.
- Add natural-language planning, visual evaluation, and an audited revision loop for the Blender workflow.
- Validate the SC2 bridge against a real project format; add an audited MPQ/Galaxy compiler/tool adapter before enabling editor/game launch.
- Evaluate LangGraph as the default durable executor against persisted `WorkflowRun`, recovery, approval, and event migration tests.
- Add durable authenticated approvals and identity before exposing approval routes beyond loopback/private network.
- Add Tailscale/private-network deployment policy, scheduled jobs, and additional specialists only after the web operations surface is proven.

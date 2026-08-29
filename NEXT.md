# Next tasks

M14–M18 bounded gateway/PWA/security foundations are complete for this cycle. Continue with M19 only when explicitly requested.

## M18 — Secure Remote Access

Complete in this cycle:

1. Defined Tailscale (or an equivalent private overlay) as the deployment target and CIDR-based client-network model.
2. Added a remote bind policy that requires a bearer token and cannot bind raw Hermes, Qwen, Blender, SC2, Codex, or privileged-helper services.
3. Added coverage for loopback, authenticated private-network requests, rejected origins, invalid networks, and missing-token startup.
4. Documented token storage, rotation, and rollback to loopback-only mode.

The host is not enrolled in Tailscale; deployment enrollment and durable identity are intentionally deferred.

## M19 — Scheduled / Autonomous Jobs

1. Define a durable job specification with explicit owner, schedule, input, permission ceiling, and cancellation policy.
2. Reuse the existing workflow checkpoint/event/recovery boundary for one bounded scheduled workflow; do not add unrestricted background agent loops.
3. Add missed-run, overlap, pause, cancel, restart, and audit tests before enabling a real scheduler.
4. Expose schedule state and run links through the gateway only after authorization and observability contracts are complete.

## Deferred platform validation

- Configure a supported Blender executable and run the opt-in headless acceptance against a copied `.blend` file, including real controlled bpy operations.
- Add natural-language planning, visual evaluation, and an audited revision loop for the Blender workflow.
- Validate the SC2 bridge against a real project format; add an audited MPQ/Galaxy compiler/tool adapter before enabling editor/game launch.
- Evaluate LangGraph as the default durable executor against persisted `WorkflowRun`, recovery, approval, and event migration tests.
- Add durable authenticated approvals and identity before exposing approval routes beyond loopback/private network.
- Add Tailscale/private-network deployment policy, scheduled jobs, and additional specialists only after the web operations surface is proven.

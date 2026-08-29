# Next tasks

M14 bounded gateway API foundations are complete for this cycle. Continue with M15 only when explicitly requested.

## M15 — Web Chat / PWA shell

1. Create the mobile-first PWA shell under `apps/web` for Chat, Runs, Approvals, Artifacts, Models, and System views.
2. Use the existing `/api/v1` contracts, bearer token, CORS allowlist, CSRF header, pagination, artifact metadata, and SSE replay without exposing raw provider services.
3. Add browser integration tests for authenticated read/write requests, reconnecting event streams, and artifact download headers.
4. Keep loopback binding as the default and add a documented local reverse-proxy option only after the PWA contract is stable.

## M16–M17 — Operations UI

- Add run monitoring, system/model health, and artifact provenance views.
- Add mobile approval, reject, steer, pause, resume, and cancel controls with explicit confirmation.

## Deferred platform validation

- Configure a supported Blender executable and run the opt-in headless acceptance against a copied `.blend` file, including real controlled bpy operations.
- Add natural-language planning, visual evaluation, and an audited revision loop for the Blender workflow.
- Validate the SC2 bridge against a real project format; add an audited MPQ/Galaxy compiler/tool adapter before enabling editor/game launch.
- Evaluate LangGraph as the default durable executor against persisted `WorkflowRun`, recovery, approval, and event migration tests.
- Add durable authenticated approvals and identity before exposing approval routes beyond loopback/private network.
- Add Tailscale/private-network deployment policy, scheduled jobs, and additional specialists only after the web operations surface is proven.

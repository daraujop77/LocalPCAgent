# Web app boundary

The chat composer includes an independent local-Qwen reasoning selector with
Automatic, Off, Low, Medium, and High choices. Automatic preserves the mode
default; an explicit choice is sent with each request and is shown in the
response metadata. It does not alter Hermes specialist routing.

The conceptual web-app design is defined in `MasterPlan/MasterPlan.md`, sections 21–23: React/Next.js PWA direction, Chat/Runs/Approvals/Artifacts/Models/System pages, and mobile-first requirements. M14 supplies the authenticated API, filtered resources, artifact downloads, and replayable run events; M15–M17 provide the first mobile UI slices. M19 exposes bounded schedule controls and M20 exposes plan-only agent coordination through the same gateway boundary; the static shell includes bounded Schedules and Agent Plans views.

The current M15–M21 slice is a dependency-free static PWA shell: `index.html`, `styles.css`, `app.js`, `manifest.webmanifest`, `service-worker.js`, and the Jarvis core visuals in `assets/`. Serve this directory with a static server during development and point it at the gateway URL in the System view. It supports bounded multi-turn chat context, `Regular`, `Deep`, and `Fast` chat profile selection, independent `Natural` (GPT-like) and `Technical` response styles, Hermes's friendly specialist/fallback labels, server-side bounded Hermes tool results, inline rendering of approved image artifacts, run/event inspection, schedule listing with lifecycle controls, a read-only Agent Plans catalog with plan previews, monitoring cards, approval decisions with visible exact scope, mobile run controls, authenticated artifact downloads, health display, and an aggregate-only agent-planning evidence card. Hermes tool parity is exposed by the gateway contract; this static shell does not directly dispatch provider tools or bypass the gateway approval boundary.

The Monitor view reads `/api/v1/agents/metrics` as an optional authenticated resource. It shows plan-only request counts, fallback rate, step/latency summaries, failure codes, and task-type buckets without displaying task text or plan identifiers. If that route is unavailable, the card reports the gateway error while the other monitoring cards continue to load.

The Schedules view reads `/api/v1/schedules?limit=50`, shows safe schedule/run metadata without rendering scheduled task input, links the latest workflow run to its event view, and confirms every pause, resume, or cancel request before sending it. Schedule creation remains API-only until durable identity and ownership are available.

The Agent Plans view reads `/api/v1/agents` and labels the boundary `PLAN ONLY · NO EXECUTION`. It can request a bounded preview through `/api/v1/agents/plans`, but renders no run, approval, or execution control and does not persist plan text in the browser beyond the current view.

## Visual themes

The header style picker switches among three visual directions: **Terran** (industrial gunmetal and amber), **Protoss** (midnight glass, gold geometry, and cyan energy), and **Jarvis** (navy glass and holographic cyan). Jarvis is the default and gives the chat view a command-deck layout with the test render from `artifacts/blender/living-core-validation test.blend`, copied to `assets/living-core-model-test.png`. The previous `assets/living-core-model.png` remains in the repository for rollback. The PNG remains the recognizable model source; a dependency-free live HTML/CSS/canvas presentation suppresses the baked inner ring band and adds smooth breathing, independently moving circular and thunder-like elliptical paths, activation filaments, flowing tapered pulses, scan light, particles, and a sparse spacefield around it. It is not a video or animated GIF. The choice is stored in browser local storage as `personal-ai-theme`; it does not affect gateway behavior, authentication, or permissions. The visual references and design rationale are in [`docs/design/FRONTEND_THEMES.md`](../../docs/design/FRONTEND_THEMES.md).

Example local static server:

```powershell
py -3.12 -m http.server 4173 --directory apps/web
```

Keep raw Hermes, Qwen, Blender, SC2, Codex, and privileged-helper services private; the PWA uses only the `/api/v1` gateway boundary. If the gateway is reached through Tailscale, use the authenticated phone mode with its API token and approved client CIDR. The separate no-token LAN chat mode is only for an explicitly supplied RFC1918 LAN CIDR.
## Phone test

Run .\scripts\phone-test.ps1 -ClientNetwork <private-cidr> -AdvertisedAddress <pc-lan-ip> from the repository root. It starts the gateway and static PWA on private-network interfaces with a token and explicit client CIDR, prints the URLs, and stops both child processes on Ctrl+C. On the phone, open the PWA URL and set the printed gateway URL/token under Monitor > Connection settings. The helper does not change the firewall or persist credentials. Same-LAN HTTP is intended for functional testing; HTTPS through a private network such as Tailscale is required before treating the PWA as a secure installable remote app.
## Remote phone access

Install and authenticate Tailscale on both devices, then run
.\scripts\phone-test.ps1 -Tailscale. The helper discovers the PC tailnet IPv4
address, uses the private 100.64.0.0/10 client range by default, and prints
the PWA URL, gateway URL, and token. Do not use public port forwarding or
Tailscale Funnel. HTTPS is still required for a secure installable PWA.

The one-command launcher also supports `.\Start-Phone-App.cmd --tailscale`.
When the phone PWA is opened on port 4174, it automatically derives the
gateway host and port 8001 from the URL; enter only the printed bearer token
under Monitor > Connection settings.

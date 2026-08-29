# Web app boundary

The conceptual web-app design is defined in `MasterPlan/MasterPlan.md`, sections 21–23: React/Next.js PWA direction, Chat/Runs/Approvals/Artifacts/Models/System pages, and mobile-first requirements. M14 supplies the authenticated API, filtered resources, artifact downloads, and replayable run events; M15–M17 provide the first mobile UI slices.

The current M15–M17 slice is a dependency-free static PWA shell: `index.html`, `styles.css`, `app.js`, `manifest.webmanifest`, and `service-worker.js`. Serve this directory with a static server during development and point it at the gateway URL in the System view. It supports chat, run/event inspection, monitoring cards, approval decisions, mobile run controls, artifact downloads, and health display.

Example local static server:

```powershell
py -3.12 -m http.server 4173 --directory apps/web
```

Keep raw Hermes, Qwen, Blender, SC2, Codex, and privileged-helper services private; the PWA uses only the `/api/v1` gateway boundary. If the gateway is later reached through Tailscale, configure its API token and approved client CIDR before enabling remote binding.

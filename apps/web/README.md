# Web app boundary

The conceptual web-app design is defined in `MasterPlan/MasterPlan.md`, sections 21–23: React/Next.js PWA direction, Chat/Runs/Approvals/Artifacts/Models/System pages, and mobile-first requirements. The mobile-friendly PWA shell is the next M15 task; M14 supplies the authenticated API, filtered resources, artifact downloads, and replayable run events.

The repository intentionally has no frontend build tool yet. Keep raw Hermes, Qwen, Blender, SC2, and privileged-helper services private; the future PWA must use the `/api/v1` gateway boundary.

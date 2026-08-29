# Next tasks

M0 through M4 are complete. The next bounded milestone is M5 — Blender Bridge. Do not begin M5 without explicit instruction.

1. Inspect the installed Blender version, executable paths, Python environment, and any available Blender MCP server without changing a scene.
2. Define Blender contracts for scene inspection, controlled `bpy` execution, working-copy creation, preview rendering, saving, and artifact metadata.
3. Add M5 Blender actions to `policies/permissions.yaml` with read-only inspection automatic and every scene/file mutation centrally approval-gated.
4. Implement a non-GUI Blender backend using `bpy`, Blender background mode, or MCP; mouse/keyboard automation remains fallback-only.
5. Create an isolated test `.blend` fixture and always duplicate it before mutation. Never overwrite the source fixture.
6. Implement the bounded acceptance path: inspect scene, duplicate working file, modify a cube and material, position a camera, render a preview, save the new `.blend`, and report artifacts.
7. Add deterministic unit tests with a fake backend and an opt-in live Blender acceptance script. Verify permission denial never starts Blender.
8. Update the handoff documents with exact M5 behavior and limitations, then stop before M6.

## Deferred validation

- Run `scripts/pc-acceptance.ps1` only when interactive Notepad control is intentionally desired.
- A future authenticated UI may make approval decisions; M4's local approval API is not a remote-access authorization system.
- Durable approvals and audit storage belong with later event/workflow persistence, not M5.

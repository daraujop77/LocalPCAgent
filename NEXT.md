# Next tasks

M0, M1, M2, and M3 are complete. The next bounded milestone is M4 — Permission System. Do not begin M4 without explicit instruction.

1. Replace the temporary `approval_granted` flags with a centralized permission-policy service and approval-request contract.
2. Move tool/action permission levels and PC application/PowerShell allowlists into validated configuration owned by that service.
3. Add approval lifecycle states — requested, accepted, rejected, expired, and cancelled — with correlation IDs and visible audit records.
4. Define the constrained privileged-helper protocol; keep the main gateway non-administrator and make helper absence fail closed.
5. Add tests proving safe actions run automatically, destructive actions pause, rejected approvals do not execute, and privileged actions cannot bypass policy.
6. Update `TOOL_CONTRACTS.md`, `ARCHITECTURE.md`, `STATUS.md`, and `DECISIONS.md` with the verified M4 behavior.

## Deferred validation

- Run `scripts/pc-acceptance.ps1` only when an interactive Notepad check is intentionally desired.
- A future cycle may add a live Codex fixture acceptance, but it must use an isolated test repository and explicit approval.

# Next tasks

M0 is complete. The following bounded tasks are proposed for M1 only; do not start them without explicit instruction.

1. Select and document the Hermes integration boundary without exposing raw Hermes endpoints.
2. Add a local Qwen client interface with a configurable local endpoint and a safe unavailable-backend response.
3. Implement deterministic model-routing rules for the M1 task categories and log the selected model, reason, fallback, and outcome.
4. Add a minimal local chat request/response contract and gateway route with structured errors.
5. Add integration tests using a fake local-model backend; no live model or cloud credential should be required for CI.
6. Update `TOOL_CONTRACTS.md`, `STATUS.md`, and `DECISIONS.md` with the actual M1 backend choice and test results.


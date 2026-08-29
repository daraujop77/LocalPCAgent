# Next tasks

M1 is complete. The following bounded tasks are proposed for M2 only; do not start them without explicit instruction.

1. Define the Codex handoff contract: repository path, task, starting revision, constraints, result, and approval boundary.
2. Add a provider interface and fake Codex backend so delegation can be tested without external credentials.
3. Implement a controlled coding-task handoff that keeps changes observable and returns changed files, test results, and a summary.
4. Add a test-repository acceptance flow where Codex modifies a fixture and the gateway reports the result.
5. Add failure handling for unavailable Codex, rejected handoffs, failed tests, and partial results.
6. Update TOOL_CONTRACTS.md, STATUS.md, and DECISIONS.md with the verified M2 handoff behavior.


# Privileged helper boundary

This directory intentionally contains no executable helper. The importable M4 boundary is in `services/privileged_helper`; its default backend is disabled and performs no elevated work.

Any future implementation must preserve all of these constraints:

- central level-3 scoped approval before transport invocation;
- a helper-side operation allowlist and independent argument validation;
- an authenticated constrained local transport rather than administrator shell access;
- non-administrator gateway/main AI process;
- structured audit/result records and fail-closed behavior when unavailable.

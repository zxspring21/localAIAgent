# Safe Tools plugin

Deny high-risk skills by default (`run_github_code`). Agent file writes stay inside the per-run sandbox.

Hooks: `PreToolUse` blocks listed skills. Remove a name from `hooks.json` to allow it.

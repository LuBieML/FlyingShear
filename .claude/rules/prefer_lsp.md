# Prefer LSP over Grep for Symbol Navigation

## Rules
- When searching for symbol definitions, finding references/usages of a class, function, or variable, or navigating imports, **ALWAYS** use LSP-based navigation tools (e.g., `goToDefinition`, `findReferences`, semantic symbols search).
- Do **NOT** use `grep` or `rg` for symbol navigation or locating code definitions.
- You may only use `grep` or `rg` for text-based queries, such as searching for log statements, comments, configuration/JSON keys, or literal error strings.
- If LSP is unavailable or fails, document why and fall back to `grep`.

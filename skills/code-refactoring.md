---
name: code-refactoring
description: Improve internal code structure without changing external behavior. Use when the user wants to clean up, de-duplicate, or restructure code while keeping observable behavior identical.
when_to_use: 'clean up', 'refactor', 'this is hard to maintain', 'reduce duplication'.
---

# Code Refactoring

Change structure, preserve behavior. Tests are the safety net.

## When to use
- "clean up", "refactor", "this is hard to maintain", "reduce duplication".

## Steps
1. **Establish a baseline** — Ensure the code under refactor has meaningful tests (or add them first). Run and confirm green.
2. **Pick one refactoring** — Small, well-known, isolated. Examples:
   - Extract function / method.
   - Remove duplication (DRY where it is genuinely the same intent).
   - Rename for clarity.
   - Replace magic numbers/strings with named constants.
   - Simplify conditional logic (guard clauses, boolean expressions).
   - Move related logic together; reduce coupling between modules.
3. **Apply it** — Make the single change. Keep the diff small and reviewable.
4. **Verify** — Re-run the full test suite; it must stay green. If red, stop and investigate.
5. **Repeat** — One refactoring at a time until the target area is done.

## Rules
- No behavior change in a refactoring step. If behavior must change, that is a feature/bug task, not a refactor.
- Do not mix refactor with new functionality in the same change.
- Keep changes reviewable; prefer many small commits to one giant rewrite.

## Stop conditions
- Target area is refactored and tests remain green → stop and summarize the improvements.

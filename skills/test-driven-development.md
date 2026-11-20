---
name: test-driven-development
description: Enforce test-first discipline: write a failing test, then the minimum code to make it pass, then refactor. Use when implementing a feature or fixing a bug where behavior must be verified.
when_to_use: Implementing a new feature or fixing a bug that has observable behavior.
---

# Test-Driven Development

Red → Green → Refactor. No implementation before a failing test.

## When to use
- Implementing a new feature or fixing a bug that has observable behavior.

## Steps (per unit of behavior)
1. **Red** — Write the smallest test that captures the desired behavior; run it and confirm it fails for the right reason.
2. **Green** — Write the minimum code to make the test pass. No extra features.
3. **Verify** — Run the new test plus the existing suite; all must pass.
4. **Refactor** — Clean up while tests stay green. No behavior change here.
5. **Repeat** — Move to the next behavior.

## Rules
- One behavior per test; name it to state intent.
- If you cannot express the behavior as a test, stop and clarify the spec first.
- Keep tests fast and deterministic; isolate external I/O.

## Stop conditions
- Desired behaviors all have passing tests → stop.
- A test that cannot be made to pass for a legitimate reason → report the spec bug; do not weaken the test to pass.

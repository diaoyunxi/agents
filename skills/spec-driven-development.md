---
name: spec-driven-development
description: Drive implementation from a written specification so the code matches the documented contract. Use when the user wants to build a feature, API, or module and the spec (input/output, behavior, edge cases) is not yet written down.
when_to_use: Starting a feature/API/module where the contract is not documented. A task keeps drifting from what was agreed.
---

# Spec-Driven Development

Write and keep a spec as the source of truth; implement against it.

## When to use
- Starting a feature/API/module where the contract is not documented.
- A task keeps drifting from what was agreed.

## Steps
1. **Write the spec first**, as a short document (or file) covering:
   - Purpose and non-goals.
   - Inputs and outputs (exact shapes/types).
   - Behavior and edge cases, each with expected outcome.
   - Error and failure modes.
   - Acceptance criteria (concrete, testable).
2. **Get agreement** — Confirm the spec before coding. Stop if not.
3. **Map implementation** — Each spec item maps to a function/test. No untracked work.
4. **Verify against spec** — After implementing, walk every spec item and confirm the code satisfies it. Report any mismatch.
5. **Update the spec** — If behavior must change, update the spec first, then the code.

## Stop conditions
- All spec items pass → stop.
- A spec item cannot be met → report which one and why; do not silently skip it.

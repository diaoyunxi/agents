---
name: executing-plans
description: Execute an approved structured plan strictly step by step, verifying each step before moving on. Use when the user has a written plan (or invokes writing-plans) and wants it carried out without drift.
when_to_use: A plan exists (from writing-plans or the user) and the user says 'execute it' / 'go ahead'.
---

# Executing Plans

Carry out an approved plan strictly, step by step, with verification.

## When to use
- A plan exists (from writing-plans or the user) and the user says "execute it" / "go ahead".

## Steps
1. **Load the plan** — Identify the current step and its verification.
2. **Execute one step at a time** — Do only that step's work.
3. **Verify** — Run the step's verification before starting the next. If it fails, stop and fix within this step.
4. **Update progress** — Mark the step done; note any deviations.
5. **Advance only on green** — Do not move to the next step while the current one is unverified.

## Deviation handling
- If a step is impossible as written, stop and report: which step, why, and the proposed change. Wait for approval to adjust the plan.
- If an unexpected problem arises that is out of scope, record it and continue only with in-scope steps; report the rest.

## Stop conditions
- All steps verified → stop and summarize what was done and any deviations.

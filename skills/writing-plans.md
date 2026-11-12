---
name: writing-plans
description: Turn a requirement or goal into a structured, ordered execution plan before writing code. Use when the user asks to plan a task, break work into steps, or outline how to implement a feature/fix without executing it yet.
when_to_use: 'make a plan', 'how would you approach X', 'outline the steps'.
---

# Writing Plans

Produce a structured, executable plan before implementation.

## When to use
- "make a plan", "how would you approach X", "outline the steps".

## Steps
1. **State the goal** in one sentence.
2. **Decompose** into ordered steps. Each step has:
   - A short title.
   - What it changes (files/areas).
   - Verification (how you'll know it's done).
   - Dependencies on earlier steps.
3. **Identify risks** — the top 1-3 things that could break, and the mitigation.
4. **Size it** — estimate relative effort per step (S/M/L).
5. **Emit the plan** as a numbered checklist the user can approve or adjust.

## Rules
- Do not start implementing until the plan is approved, unless told to proceed.
- Each step is small enough to verify independently.
- Keep the plan in the working language of the task.

---
name: ask-questions-if-underspecified
description: Before implementing, ask focused clarifying questions when requirements are ambiguous, missing, or conflicting. Use when the user gives an underspecified feature request and building on assumptions would risk the wrong design.
when_to_use: Feature request is vague on scope, data, success criteria, or constraints. Two or more plausible interpretations exist and they differ materially. The cost of guessing wrong is high (architecture, API shape, data model).
---

# Ask Questions if Underspecified

Do not code on assumptions when the request is underspecified. Surface the gaps first.

## When to use
- Feature request is vague on scope, data, success criteria, or constraints.
- Two or more plausible interpretations exist and they differ materially.
- The cost of guessing wrong is high (architecture, API shape, data model).

## Steps
1. **Restate the intent in 1-2 sentences** to confirm shared understanding.
2. **List unknowns** that block a confident design: scope, inputs/outputs, edge cases, non-functional requirements (perf, security, i18n), and constraints.
3. **Ask 3-5 sharp questions** in one batch. Each question should be answerable with a short concrete reply. Prefer multiple-choice where it helps.
4. **Record the answers** verbatim, then state the plan in 3-5 bullets before coding.
5. **Stop** and wait for confirmation if the answers change the plan materially.

## Failure handling
- If the user says "just decide", state the assumption explicitly in one line before proceeding, and keep it easy to reverse.
- Never invent constraints the user did not state.
